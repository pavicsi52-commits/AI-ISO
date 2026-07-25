"""Span exporters.

Per docs/024_Enterprise_Telemetry_Framework.md.txt "EXPORTERS": OTLP,
Console, JSON ("Future": Jaeger, Grafana Tempo, Zipkin, Azure Monitor,
AWS X-Ray, Google Cloud Trace -- explicitly out of scope, and per "DO
NOT IMPLEMENT" this framework must not run a Jaeger/Tempo/Prometheus
server itself). "Exporters shall be configurable" -- :func:`create_exporter`
is the one place a service picks its exporter by name, driven by
:class:`~shared_core.config.settings.TelemetrySettings`.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SpanExporter, SpanExportResult

from shared_core.telemetry.exceptions import ExporterConfigurationError

_KNOWN_EXPORTER_TYPES = ("console", "otlp", "json")


class JsonFileSpanExporter(SpanExporter):
    """Writes finished spans as newline-delimited JSON to a file ("JSON" exporter).

    Not a standard OpenTelemetry exporter -- the SDK ships Console and
    OTLP but no line-oriented JSON file writer, and docs/024 lists JSON
    as its own exporter type distinct from Console (human-readable
    stdout) and OTLP (a real collector), so a small, honest
    implementation is written here rather than overloading
    :class:`~opentelemetry.sdk.trace.export.ConsoleSpanExporter`'s
    formatting for a different purpose.
    """

    def __init__(self, path: str | Path):
        self._path = Path(path)
        self._lock = threading.Lock()

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        lines = [json.dumps(_span_to_dict(span)) for span in spans]
        try:
            with self._lock, self._path.open("a", encoding="utf-8") as handle:
                for line in lines:
                    handle.write(line + "\n")
        except OSError:
            return SpanExportResult.FAILURE
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        pass

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        return True


def _span_to_dict(span: ReadableSpan) -> dict[str, Any]:
    context = span.get_span_context()
    return {
        "name": span.name,
        "trace_id": format(context.trace_id, "032x") if context else None,
        "span_id": format(context.span_id, "016x") if context else None,
        "parent_span_id": (
            format(span.parent.span_id, "016x") if span.parent is not None else None
        ),
        "start_time": span.start_time,
        "end_time": span.end_time,
        "attributes": dict(span.attributes or {}),
        "status": span.status.status_code.name if span.status else None,
    }


def console_exporter() -> ConsoleSpanExporter:
    """The default exporter -- every service gets spans locally even with no collector."""
    return ConsoleSpanExporter()


def json_file_exporter(path: str | Path) -> JsonFileSpanExporter:
    """A JSON-lines file exporter, for local inspection or shipping via a log collector."""
    return JsonFileSpanExporter(path)


def otlp_exporter(*, endpoint: str, headers: dict[str, str] | None = None) -> SpanExporter:
    """An OTLP/HTTP exporter, for a real collector (Prompt 024 "OPENTELEMETRY": OTLP Exporter)."""
    if not endpoint:
        raise ExporterConfigurationError("otlp_exporter requires a non-empty endpoint.")
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import (  # noqa: PLC0415
        OTLPSpanExporter,
    )

    return OTLPSpanExporter(endpoint=endpoint, headers=headers)


def create_exporter(
    exporter_type: str, *, otlp_endpoint: str = "", json_path: str | Path = "spans.jsonl"
) -> SpanExporter:
    """Build the exporter named by *exporter_type* ("Exporters shall be configurable").

    Mirrors :class:`~shared_core.config.settings.TelemetrySettings`'s
    ``telemetry_exporter`` field -- the one place a service turns that
    setting into a real exporter instance.
    """
    if exporter_type == "console":
        return console_exporter()
    if exporter_type == "json":
        return json_file_exporter(json_path)
    if exporter_type == "otlp":
        return otlp_exporter(endpoint=otlp_endpoint)
    raise ExporterConfigurationError(
        f"Unknown exporter type {exporter_type!r}; expected one of {_KNOWN_EXPORTER_TYPES}."
    )


__all__ = [
    "JsonFileSpanExporter",
    "console_exporter",
    "create_exporter",
    "json_file_exporter",
    "otlp_exporter",
]
