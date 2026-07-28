"""AI assistant telemetry.

Per docs/046 "TELEMETRY": Prompt Execution, RAG Retrieval, Embedding
Search, Tool Calls, Agent Execution, Model Latency, Streaming
Responses. No dedicated :class:`~shared_core.telemetry.span.SpanType`
member exists for any of these, so each falls back to ``REST_API`` or
``BACKGROUND_JOB`` with a distinguishing span name -- the same choice
every prior AI-IOS service made for the same reason.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry.trace import Span, Tracer
from shared_core.telemetry.span import SpanType, start_span


@contextmanager
def trace_prompt_execution(
    tracer: Tracer, *, prompt_id: str, **attributes: object
) -> Iterator[Span]:
    """Trace one prompt template rendering and execution."""
    with start_span(
        tracer,
        "ai.prompt_execution",
        span_type=SpanType.REST_API,
        prompt_id=prompt_id,
        **attributes,
    ) as span:
        yield span


@contextmanager
def trace_rag_retrieval(tracer: Tracer, *, strategy: str, **attributes: object) -> Iterator[Span]:
    """Trace one RAG retrieval pass."""
    with start_span(
        tracer,
        "ai.rag_retrieval",
        span_type=SpanType.BACKGROUND_JOB,
        strategy=strategy,
        **attributes,
    ) as span:
        yield span


@contextmanager
def trace_embedding_search(tracer: Tracer, *, top_k: int, **attributes: object) -> Iterator[Span]:
    """Trace one vector similarity search."""
    with start_span(
        tracer,
        "ai.embedding_search",
        span_type=SpanType.BACKGROUND_JOB,
        top_k=top_k,
        **attributes,
    ) as span:
        yield span


@contextmanager
def trace_tool_call(tracer: Tracer, *, tool_key: str, **attributes: object) -> Iterator[Span]:
    """Trace one tool invocation."""
    with start_span(
        tracer,
        "ai.tool_call",
        span_type=SpanType.BACKGROUND_JOB,
        tool_key=tool_key,
        **attributes,
    ) as span:
        yield span


@contextmanager
def trace_agent_execution(
    tracer: Tracer, *, agent_type: str, **attributes: object
) -> Iterator[Span]:
    """Trace one agent's own task."""
    with start_span(
        tracer,
        "ai.agent_execution",
        span_type=SpanType.BACKGROUND_JOB,
        agent_type=agent_type,
        **attributes,
    ) as span:
        yield span


@contextmanager
def trace_model_call(
    tracer: Tracer, *, provider: str, model: str, **attributes: object
) -> Iterator[Span]:
    """Trace one model provider call ("Model Latency")."""
    with start_span(
        tracer,
        "ai.model_call",
        span_type=SpanType.BACKGROUND_JOB,
        provider=provider,
        model=model,
        **attributes,
    ) as span:
        yield span


@contextmanager
def trace_streaming_response(
    tracer: Tracer, *, provider: str, **attributes: object
) -> Iterator[Span]:
    """Trace one streamed response ("Streaming Responses")."""
    with start_span(
        tracer,
        "ai.streaming_response",
        span_type=SpanType.BACKGROUND_JOB,
        provider=provider,
        **attributes,
    ) as span:
        yield span


__all__ = [
    "trace_agent_execution",
    "trace_embedding_search",
    "trace_model_call",
    "trace_prompt_execution",
    "trace_rag_retrieval",
    "trace_streaming_response",
    "trace_tool_call",
]
