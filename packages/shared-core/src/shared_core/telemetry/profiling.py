"""Performance profiling.

Per docs/024_Enterprise_Telemetry_Framework.md.txt "PERFORMANCE
PROFILING": REST APIs, Database Queries, Redis Operations, RabbitMQ
Operations, Neo4j Queries, Workflow/Automation/Validation Execution, AI
Inference, Connector/Plugin Execution, Storage Operations.

Two levels, matching real-world cost: :func:`measure_duration_ms` is the
cheap, always-on wall-clock timer every span/decorator in this framework
uses (backs ``@measure``/``@profile`` and every ``@track_*`` decorator);
:class:`DeepProfile` is the expensive, opt-in
:mod:`cProfile`-based profiler for genuinely investigating *why* one
specific call is slow, never meant to run on every request.
"""

from __future__ import annotations

import cProfile
import io
import pstats
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProfileResult:
    """The outcome of timing one block of code."""

    label: str
    duration_ms: float


@contextmanager
def measure_duration_ms(label: str) -> Iterator[ProfileResult]:
    """Time a block of code, yielding a :class:`ProfileResult` filled in on exit.

    The yielded object's ``duration_ms`` is only valid *after* the
    ``with`` block exits -- read it afterward, not inside.
    """
    result = ProfileResult(label=label, duration_ms=0.0)
    start = time.perf_counter()
    try:
        yield result
    finally:
        object.__setattr__(result, "duration_ms", (time.perf_counter() - start) * 1000)


class DeepProfile:
    """Wraps :mod:`cProfile` for one-off, opt-in deep profiling of a code block.

    Deliberately not wired into any decorator applied broadly -- running
    this on every request would defeat "Telemetry must have minimal
    runtime overhead" (docs/024 "TELEMETRY PRINCIPLES").
    """

    def __init__(self) -> None:
        self._profiler = cProfile.Profile()

    def __enter__(self) -> DeepProfile:
        self._profiler.enable()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._profiler.disable()

    def stats(self, *, top_n: int = 20, sort_by: str = "cumulative") -> str:
        """Return the top *top_n* functions by *sort_by*, formatted as text."""
        stream = io.StringIO()
        stats = pstats.Stats(self._profiler, stream=stream)
        stats.sort_stats(sort_by)
        stats.print_stats(top_n)
        return stream.getvalue()


__all__ = ["DeepProfile", "ProfileResult", "measure_duration_ms"]
