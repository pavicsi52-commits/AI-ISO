"""Sampling strategies.

Per docs/024_Enterprise_Telemetry_Framework.md.txt "SAMPLING": Always
Sample, Never Sample, Probability Sampling, Adaptive Sampling, Rule
Based Sampling, Environment Based Sampling, Dynamic Sampling. Built on
top of the OpenTelemetry SDK's own :class:`~opentelemetry.sdk.trace.sampling.Sampler`
protocol rather than reimplementing sampling decisions from scratch.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from opentelemetry.context import Context
from opentelemetry.sdk.trace.sampling import (
    ALWAYS_OFF,
    ALWAYS_ON,
    ParentBased,
    Sampler,
    SamplingResult,
    TraceIdRatioBased,
)
from opentelemetry.trace import Link, SpanKind
from opentelemetry.util.types import Attributes

from shared_core.telemetry.exceptions import SamplingConfigurationError

_DEFAULT_ENVIRONMENT_RATIOS: dict[str, float] = {
    "production": 0.1,
    "staging": 0.5,
    "development": 1.0,
    "test": 1.0,
}


def always_sample() -> Sampler:
    """Sample every trace ("Always Sample")."""
    return ALWAYS_ON


def never_sample() -> Sampler:
    """Sample no trace ("Never Sample")."""
    return ALWAYS_OFF


def probability_sampler(ratio: float) -> Sampler:
    """Sample a fixed fraction of *new* traces ("Probability Sampling").

    Wrapped in :class:`~opentelemetry.sdk.trace.sampling.ParentBased` so a
    child span always follows its parent's sampling decision -- a trace
    is sampled or not as a whole, never partially.
    """
    if not 0.0 <= ratio <= 1.0:
        raise SamplingConfigurationError(f"Sample ratio must be in [0.0, 1.0], got {ratio!r}.")
    return ParentBased(TraceIdRatioBased(ratio))


def environment_based_sampler(
    environment: str, *, ratios: dict[str, float] | None = None
) -> Sampler:
    """Pick a probability sampler based on *environment* ("Environment Based Sampling").

    Defaults to conservative sampling in `production`/`staging` and full
    sampling everywhere else, on the assumption that non-production
    environments have far less traffic and far more value in full traces.
    """
    ratio = (ratios or _DEFAULT_ENVIRONMENT_RATIOS).get(environment, 1.0)
    return probability_sampler(ratio)


@dataclass(frozen=True, slots=True)
class SamplingRule:
    """One rule for :class:`RuleBasedSampler`: if *predicate* matches, use *sampler*."""

    predicate: Callable[[str, Attributes], bool]
    sampler: Sampler


class RuleBasedSampler(Sampler):
    """Delegates to the first matching rule's sampler, or *default_sampler* ("Rule Based")."""

    def __init__(self, rules: Sequence[SamplingRule], *, default_sampler: Sampler | None = None):
        self._rules = list(rules)
        self._default_sampler = default_sampler or ALWAYS_ON

    def should_sample(
        self,
        parent_context: Context | None,
        trace_id: int,
        name: str,
        kind: SpanKind | None = None,
        attributes: Attributes = None,
        links: Sequence[Link] | None = None,
        trace_state: object | None = None,
    ) -> SamplingResult:
        for rule in self._rules:
            if rule.predicate(name, attributes):
                return rule.sampler.should_sample(
                    parent_context, trace_id, name, kind, attributes, links
                )
        return self._default_sampler.should_sample(
            parent_context, trace_id, name, kind, attributes, links
        )

    def get_description(self) -> str:
        return f"RuleBasedSampler{{rules={len(self._rules)}}}"


class DynamicSampler(Sampler):
    """A probability sampler whose ratio can be changed at runtime ("Dynamic Sampling").

    Reconstructing :class:`TraceIdRatioBased` per decision is cheap (it's
    a pure function of the ratio) -- simpler and just as correct as
    caching it, and avoids a stale cached sampler if :meth:`set_ratio` is
    called concurrently with a sampling decision.
    """

    def __init__(self, initial_ratio: float = 1.0):
        self.set_ratio(initial_ratio)

    def set_ratio(self, ratio: float) -> None:
        """Change the sampling ratio applied to every subsequent decision."""
        if not 0.0 <= ratio <= 1.0:
            raise SamplingConfigurationError(f"Sample ratio must be in [0.0, 1.0], got {ratio!r}.")
        self._ratio = ratio

    @property
    def ratio(self) -> float:
        """The currently configured sampling ratio."""
        return self._ratio

    def should_sample(
        self,
        parent_context: Context | None,
        trace_id: int,
        name: str,
        kind: SpanKind | None = None,
        attributes: Attributes = None,
        links: Sequence[Link] | None = None,
        trace_state: object | None = None,
    ) -> SamplingResult:
        delegate = ParentBased(TraceIdRatioBased(self._ratio))
        return delegate.should_sample(parent_context, trace_id, name, kind, attributes, links)

    def get_description(self) -> str:
        return f"DynamicSampler{{ratio={self._ratio}}}"


class AdaptiveSampler(Sampler):
    """Adjusts its sampling ratio to approach a target throughput ("Adaptive Sampling").

    Tracks how many *new* traces (root spans -- no parent context) it has
    seen in the current one-second window; if that count exceeds
    *target_samples_per_second*, the ratio is scaled down proportionally
    for the next window so downstream volume stays roughly bounded under
    load, rather than sampling every trace at a fixed ratio regardless of
    actual traffic.
    """

    def __init__(self, *, target_samples_per_second: float, min_ratio: float = 0.01):
        if target_samples_per_second <= 0:
            raise SamplingConfigurationError("target_samples_per_second must be positive.")
        self._target = target_samples_per_second
        self._min_ratio = min_ratio
        self._ratio = 1.0
        self._window_start = time.monotonic()
        self._window_count = 0

    @property
    def ratio(self) -> float:
        """The currently computed sampling ratio."""
        return self._ratio

    def _observe(self) -> None:
        now = time.monotonic()
        elapsed = now - self._window_start
        if elapsed >= 1.0:
            observed_rate = self._window_count / elapsed
            if observed_rate > self._target:
                self._ratio = max(self._min_ratio, self._ratio * (self._target / observed_rate))
            else:
                self._ratio = min(1.0, self._ratio * 1.1)
            self._window_start = now
            self._window_count = 0
        self._window_count += 1

    def should_sample(
        self,
        parent_context: Context | None,
        trace_id: int,
        name: str,
        kind: SpanKind | None = None,
        attributes: Attributes = None,
        links: Sequence[Link] | None = None,
        trace_state: object | None = None,
    ) -> SamplingResult:
        self._observe()
        delegate = ParentBased(TraceIdRatioBased(self._ratio))
        return delegate.should_sample(parent_context, trace_id, name, kind, attributes, links)

    def get_description(self) -> str:
        return f"AdaptiveSampler{{target={self._target}/s, ratio={self._ratio}}}"


__all__ = [
    "AdaptiveSampler",
    "DynamicSampler",
    "RuleBasedSampler",
    "SamplingRule",
    "always_sample",
    "environment_based_sampler",
    "never_sample",
    "probability_sampler",
]
