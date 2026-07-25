"""Tests for decorators.py."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Tracer
from shared_core.metrics.registry import create_histogram
from shared_core.telemetry.decorators import (
    measure,
    profile,
    span,
    trace,
    track_ai,
    track_automation,
    track_cache,
    track_connector,
    track_database,
    track_plugin,
    track_queue,
    track_storage,
    track_validation,
    track_workflow,
)


def _tracer_and_exporter() -> tuple[Tracer, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider.get_tracer(__name__), exporter


_AsyncStrFunc = Callable[[], Awaitable[str]]
_TrackDecoratorFactory = Callable[[Tracer], Callable[[_AsyncStrFunc], _AsyncStrFunc]]


async def test_trace_decorator_starts_a_root_trace_named_after_the_function() -> None:
    tracer, exporter = _tracer_and_exporter()

    @trace(tracer)
    async def do_work() -> str:
        return "done"

    result = await do_work()

    assert result == "done"
    spans = exporter.get_finished_spans()
    assert spans[0].name == "do_work"
    assert spans[0].parent is None


async def test_trace_decorator_honors_an_explicit_name() -> None:
    tracer, exporter = _tracer_and_exporter()

    @trace(tracer, name="custom-op")
    async def do_work() -> None:
        pass

    await do_work()

    assert exporter.get_finished_spans()[0].name == "custom-op"


async def test_span_decorator_attaches_under_the_currently_active_span() -> None:
    tracer, exporter = _tracer_and_exporter()

    @span(tracer)
    async def inner() -> None:
        pass

    with tracer.start_as_current_span("outer"):
        await inner()

    spans = {s.name: s for s in exporter.get_finished_spans()}
    assert spans["inner"].parent is not None


async def test_measure_decorator_observes_the_functions_duration() -> None:
    histogram = create_histogram("test_measure_decorator_seconds", "test")

    @measure(histogram)
    async def do_work() -> str:
        return "done"

    before = histogram._sum.get()
    result = await do_work()
    after = histogram._sum.get()

    assert result == "done"
    assert after >= before


async def test_profile_decorator_returns_the_result_and_stats_text() -> None:
    @profile()
    async def do_work() -> int:
        return sum(range(1000))

    result, stats = await do_work()

    assert result == sum(range(1000))
    assert "do_work" in stats


@pytest.mark.parametrize(
    "decorator_factory",
    [
        track_database,
        track_cache,
        lambda tracer: track_queue(tracer, "orders"),
        track_storage,
        lambda tracer: track_connector(tracer, "jira"),
        lambda tracer: track_plugin(tracer, "slack-notify"),
        lambda tracer: track_workflow(tracer, "onboarding"),
        lambda tracer: track_automation(tracer, "cleanup"),
        track_validation,
        lambda tracer: track_ai(tracer, "anthropic"),
    ],
)
async def test_track_decorator_wraps_the_function_in_exactly_one_span(
    decorator_factory: _TrackDecoratorFactory,
) -> None:
    tracer, exporter = _tracer_and_exporter()

    @decorator_factory(tracer)
    async def do_work() -> str:
        return "done"

    result = await do_work()

    assert result == "done"
    assert len(exporter.get_finished_spans()) == 1


async def test_track_decorator_reraises_and_still_ends_the_span() -> None:
    tracer, exporter = _tracer_and_exporter()

    @track_database(tracer)
    async def failing() -> None:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        await failing()

    assert len(exporter.get_finished_spans()) == 1
