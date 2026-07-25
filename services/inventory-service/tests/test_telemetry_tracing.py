"""Tests for :mod:`app.telemetry.tracing`'s span helpers.

Uses a real ``opentelemetry.sdk.trace.TracerProvider`` with an
in-memory exporter, matching this repository's established telemetry
test pattern (see ``services/secrets-management-service/tests
/test_telemetry_tracing.py``).
"""

from __future__ import annotations

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Tracer

from app.telemetry.tracing import (
    trace_export,
    trace_import,
    trace_inventory_crud,
    trace_relationship_query,
    trace_search,
    trace_synchronization,
    trace_topology_update,
)


def _provider() -> tuple[Tracer, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider.get_tracer(__name__), exporter


def test_trace_inventory_crud_includes_operation_attribute() -> None:
    tracer, exporter = _provider()

    with trace_inventory_crud(tracer, operation="create", asset_id="a-1"):
        pass

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "inventory.crud"
    assert spans[0].attributes is not None
    assert spans[0].attributes.get("operation") == "create"
    assert spans[0].attributes.get("asset_id") == "a-1"


def test_trace_topology_update() -> None:
    tracer, exporter = _provider()

    with trace_topology_update(tracer, asset_id="a-1"):
        pass

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "inventory.topology_update"


def test_trace_relationship_query_includes_query_kind() -> None:
    tracer, exporter = _provider()

    with trace_relationship_query(tracer, query_kind="neighbors"):
        pass

    spans = exporter.get_finished_spans()
    assert spans[0].name == "inventory.relationship_query"
    assert spans[0].attributes is not None
    assert spans[0].attributes.get("query_kind") == "neighbors"


def test_trace_import() -> None:
    tracer, exporter = _provider()

    with trace_import(tracer, job_id="j-1"):
        pass

    assert exporter.get_finished_spans()[0].name == "inventory.import"


def test_trace_export() -> None:
    tracer, exporter = _provider()

    with trace_export(tracer, job_id="j-1"):
        pass

    assert exporter.get_finished_spans()[0].name == "inventory.export"


def test_trace_synchronization() -> None:
    tracer, exporter = _provider()

    with trace_synchronization(tracer):
        pass

    assert exporter.get_finished_spans()[0].name == "inventory.synchronization"


def test_trace_search() -> None:
    tracer, exporter = _provider()

    with trace_search(tracer, query="alpha"):
        pass

    spans = exporter.get_finished_spans()
    assert spans[0].name == "inventory.search"
    assert spans[0].attributes is not None
    assert spans[0].attributes.get("query") == "alpha"


__all__: list[str] = []
