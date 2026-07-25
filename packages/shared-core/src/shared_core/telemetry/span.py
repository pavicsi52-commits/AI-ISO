"""Span types and the shared span-creation primitive.

Every per-subsystem helper (:mod:`shared_core.telemetry.database`,
``.cache``, ``.queue``, ``.storage``, ``.connector``, ``.plugin``,
``.workflow``, ``.automation``, ``.validation``, ``.ai``, ...) is a thin
wrapper around :func:`start_span` with its own :class:`SpanType`, kept in
one place so attribute masking ("SECURITY": never capture secrets) and
span-kind tagging are applied consistently everywhere instead of once
per subsystem file.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from enum import StrEnum
from typing import Any

from opentelemetry.trace import Span, Tracer

from shared_core.telemetry.constants import MASKED_ATTRIBUTE_VALUE, SENSITIVE_ATTRIBUTE_KEYWORDS


class SpanType(StrEnum):
    """Every span kind docs/024 "SPAN TYPES" names."""

    HTTP_REQUEST = "http_request"
    REST_API = "rest_api"
    DATABASE_QUERY = "database_query"
    CACHE_ACCESS = "cache_access"
    QUEUE_PUBLISH = "queue_publish"
    QUEUE_CONSUME = "queue_consume"
    WORKFLOW_STEP = "workflow_step"
    AUTOMATION_STEP = "automation_step"
    VALIDATION_STEP = "validation_step"
    CONNECTOR_EXECUTION = "connector_execution"
    PLUGIN_EXECUTION = "plugin_execution"
    AI_REQUEST = "ai_request"
    MODEL_INFERENCE = "model_inference"
    FILE_UPLOAD = "file_upload"
    FILE_DOWNLOAD = "file_download"
    BACKGROUND_JOB = "background_job"
    SCHEDULER_JOB = "scheduler_job"
    CLI_COMMAND = "cli_command"


def _is_sensitive(key: str) -> bool:
    lowered = key.lower()
    return any(keyword in lowered for keyword in SENSITIVE_ATTRIBUTE_KEYWORDS)


def sanitize_attributes(attributes: dict[str, Any]) -> dict[str, Any]:
    """Mask any attribute whose key looks like it carries a secret ("SECURITY").

    Matches by keyword against the attribute *name* (e.g. ``api_key``,
    ``user_password``), not its value -- this framework has no reliable
    way to detect a secret from its value alone, so callers are still
    responsible for not passing genuinely sensitive values under an
    innocuous-looking key.
    """
    return {
        key: (MASKED_ATTRIBUTE_VALUE if _is_sensitive(key) else value)
        for key, value in attributes.items()
    }


@contextmanager
def start_span(
    tracer: Tracer, name: str, *, span_type: SpanType | None = None, **attributes: Any
) -> Iterator[Span]:
    """Start a span with the given attributes, ending it on exit.

    Every span shall have a parent (docs/024 "TELEMETRY PRINCIPLES") --
    this always attaches under whatever span is currently active; use
    :func:`shared_core.telemetry.trace.start_root_trace` for the one
    deliberate exception (a trace's entry point).
    """
    sanitized = sanitize_attributes(attributes)
    if span_type is not None:
        sanitized["span.type"] = span_type.value
    with tracer.start_as_current_span(name) as span:
        for key, value in sanitized.items():
            span.set_attribute(key, value)
        yield span


__all__ = ["SpanType", "sanitize_attributes", "start_span"]
