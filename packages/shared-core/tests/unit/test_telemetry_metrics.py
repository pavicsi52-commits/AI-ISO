"""Tests for metrics.py."""

from __future__ import annotations

from opentelemetry.sdk.trace import TracerProvider
from shared_core.telemetry.metrics import (
    cache_time_seconds,
    database_time_seconds,
    observe_with_trace_exemplar,
    storage_time_seconds,
)


def test_database_time_seconds_records_an_observation() -> None:
    before = database_time_seconds.labels(operation="select")._sum.get()

    database_time_seconds.labels(operation="select").observe(0.05)

    assert database_time_seconds.labels(operation="select")._sum.get() >= before + 0.05


def test_cache_time_seconds_records_an_observation() -> None:
    before = cache_time_seconds.labels(operation="get")._sum.get()

    cache_time_seconds.labels(operation="get").observe(0.01)

    assert cache_time_seconds.labels(operation="get")._sum.get() >= before + 0.01


def test_storage_time_seconds_records_an_observation() -> None:
    before = storage_time_seconds.labels(operation="upload")._sum.get()

    storage_time_seconds.labels(operation="upload").observe(0.2)

    assert storage_time_seconds.labels(operation="upload")._sum.get() >= before + 0.2


def test_observe_with_trace_exemplar_records_a_plain_observation_with_no_active_span() -> None:
    before = database_time_seconds.labels(operation="no-trace")._sum.get()

    observe_with_trace_exemplar(database_time_seconds, 0.03, operation="no-trace")

    assert database_time_seconds.labels(operation="no-trace")._sum.get() >= before + 0.03


def test_observe_with_trace_exemplar_attaches_the_current_trace_id() -> None:
    provider = TracerProvider()
    tracer = provider.get_tracer(__name__)

    with tracer.start_as_current_span("db-op"):
        observe_with_trace_exemplar(database_time_seconds, 0.04, operation="with-trace")

    child = database_time_seconds.labels(operation="with-trace")
    exemplars = [b.get_exemplar() for b in child._buckets]
    matching = [e for e in exemplars if e is not None]
    assert len(matching) == 1
    assert "trace_id" in matching[0].labels
