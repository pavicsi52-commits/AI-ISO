"""AI Request/Model Inference span helpers.

Per docs/024_Enterprise_Telemetry_Framework.md.txt "SPAN TYPES": AI
Request, Model Inference. Instruments the future AI Engine's provider
calls and model inference without that engine depending on telemetry
itself.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry.trace import Span, Tracer

from shared_core.telemetry.span import SpanType, start_span


@contextmanager
def trace_ai_request(tracer: Tracer, provider: str, **attributes: str) -> Iterator[Span]:
    """Trace one AI provider request ("AI Request")."""
    with start_span(
        tracer,
        f"ai.request {provider}",
        span_type=SpanType.AI_REQUEST,
        provider=provider,
        **attributes,
    ) as span:
        yield span


@contextmanager
def trace_model_inference(tracer: Tracer, model_name: str, **attributes: str) -> Iterator[Span]:
    """Trace one model inference call ("Model Inference"; "PERFORMANCE PROFILING": AI Inference)."""
    with start_span(
        tracer,
        f"ai.inference {model_name}",
        span_type=SpanType.MODEL_INFERENCE,
        model_name=model_name,
        **attributes,
    ) as span:
        yield span


__all__ = ["trace_ai_request", "trace_model_inference"]
