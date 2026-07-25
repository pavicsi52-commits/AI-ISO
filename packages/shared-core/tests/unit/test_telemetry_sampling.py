"""Tests for sampling.py."""

from __future__ import annotations

import pytest
from opentelemetry.sdk.trace.sampling import Decision
from shared_core.telemetry.exceptions import SamplingConfigurationError
from shared_core.telemetry.sampling import (
    AdaptiveSampler,
    DynamicSampler,
    RuleBasedSampler,
    SamplingRule,
    always_sample,
    environment_based_sampler,
    never_sample,
    probability_sampler,
)


def _decide(sampler: object, *, trace_id: int = 1, name: str = "op", attributes: object = None):  # type: ignore[no-untyped-def]
    return sampler.should_sample(None, trace_id, name, attributes=attributes)  # type: ignore[attr-defined]


def test_always_sample_always_records_and_samples() -> None:
    result = _decide(always_sample())

    assert result.decision in (Decision.RECORD_AND_SAMPLE,)


def test_never_sample_never_samples() -> None:
    result = _decide(never_sample())

    assert result.decision == Decision.DROP


def test_probability_sampler_rejects_an_out_of_range_ratio() -> None:
    with pytest.raises(SamplingConfigurationError):
        probability_sampler(1.5)
    with pytest.raises(SamplingConfigurationError):
        probability_sampler(-0.1)


def test_probability_sampler_zero_never_samples_a_root_trace() -> None:
    sampler = probability_sampler(0.0)

    result = _decide(sampler)

    assert result.decision == Decision.DROP


def test_probability_sampler_one_always_samples_a_root_trace() -> None:
    sampler = probability_sampler(1.0)

    result = _decide(sampler)

    assert result.decision != Decision.DROP


def test_environment_based_sampler_samples_fully_in_development() -> None:
    sampler = environment_based_sampler("development")

    result = _decide(sampler)

    assert result.decision != Decision.DROP


def test_environment_based_sampler_uses_custom_ratios() -> None:
    sampler = environment_based_sampler("staging", ratios={"staging": 0.0})

    result = _decide(sampler)

    assert result.decision == Decision.DROP


def test_environment_based_sampler_defaults_unknown_environments_to_full_sampling() -> None:
    sampler = environment_based_sampler("some-custom-env")

    result = _decide(sampler)

    assert result.decision != Decision.DROP


def test_rule_based_sampler_uses_the_first_matching_rules_sampler() -> None:
    sampler = RuleBasedSampler(
        rules=[
            SamplingRule(
                predicate=lambda name, attrs: name == "health-check", sampler=never_sample()
            )
        ],
        default_sampler=always_sample(),
    )

    health_result = _decide(sampler, name="health-check")
    other_result = _decide(sampler, name="checkout")

    assert health_result.decision == Decision.DROP
    assert other_result.decision != Decision.DROP


def test_rule_based_sampler_falls_through_to_default_when_no_rule_matches() -> None:
    sampler = RuleBasedSampler(rules=[], default_sampler=always_sample())

    result = _decide(sampler)

    assert result.decision != Decision.DROP


def test_dynamic_sampler_reflects_the_ratio_at_decision_time() -> None:
    sampler = DynamicSampler(initial_ratio=1.0)
    assert _decide(sampler).decision != Decision.DROP

    sampler.set_ratio(0.0)
    assert _decide(sampler).decision == Decision.DROP

    sampler.set_ratio(1.0)
    assert _decide(sampler).decision != Decision.DROP


def test_dynamic_sampler_rejects_an_out_of_range_ratio() -> None:
    sampler = DynamicSampler()

    with pytest.raises(SamplingConfigurationError):
        sampler.set_ratio(2.0)


def test_adaptive_sampler_rejects_a_non_positive_target() -> None:
    with pytest.raises(SamplingConfigurationError):
        AdaptiveSampler(target_samples_per_second=0)


def test_adaptive_sampler_starts_at_full_ratio() -> None:
    sampler = AdaptiveSampler(target_samples_per_second=100.0)

    assert sampler.ratio == 1.0


def test_adaptive_sampler_scales_down_after_a_burst_over_target() -> None:
    sampler = AdaptiveSampler(target_samples_per_second=10.0, min_ratio=0.01)
    # Simulate 1000 observations already counted over the last ~1 second
    # (far above the 10/s target), then let the window close on the next call.
    sampler._window_count = 1000
    sampler._window_start -= 1.0

    sampler._observe()

    assert sampler.ratio < 1.0
