"""AI agent platform telemetry (docs/060 "TELEMETRY"): Planning Time,
Reasoning, Tool Calls, Model Calls, Memory Access, Task Execution,
Approval Flow.

Integrates ``shared_core.telemetry`` (Prompt 024). "Model Calls" reuses
``shared_core.telemetry.ai.trace_ai_request``/``trace_model_inference``
directly (re-exported below) rather than redefining an equivalent --
this platform's own established AI-request/model-inference span shape
already covers it exactly.

**Every call below passes attributes via ``**{...}``, never a literal
``attributes={...}`` keyword.** ``start_span``'s own signature is
``start_span(tracer, name, *, span_type=None, **attributes)`` -- there is
no parameter actually named ``attributes``, only that catch-all. Passing
one anyway silently drops every attribute onto the floor instead of
raising -- a confirmed, repo-wide defect in every AI-IOS service before
Prompt 054. This copy was written correct from the start.

**Spans carry identifiers and outcomes, never raw prompts, model
output, or memory content.** An agent's own request/response and
remembered facts may carry another tenant's sensitive data; a tracing
backend has different retention and different access rules than this
service's own database does.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry.trace import Span, Tracer
from shared_core.telemetry.ai import trace_ai_request, trace_model_inference
from shared_core.telemetry.span import SpanType, start_span


@contextmanager
def trace_planning(
    tracer: Tracer, *, agent_id: str, mode: str, **attributes: object
) -> Iterator[Span]:
    """Span the planning phase of one reasoning run ("Planning Time")."""
    with start_span(
        tracer,
        "agent.planning",
        span_type=SpanType.WORKFLOW_STEP,
        **{"agent.agent_id": agent_id, "agent.reasoning_mode": mode, **attributes},
    ) as span:
        yield span


@contextmanager
def trace_reasoning(
    tracer: Tracer, *, agent_id: str, mode: str, execution_id: str, **attributes: object
) -> Iterator[Span]:
    """Span one full reasoning-mode run ("Reasoning")."""
    with start_span(
        tracer,
        "agent.reasoning",
        span_type=SpanType.WORKFLOW_STEP,
        **{
            "agent.agent_id": agent_id,
            "agent.reasoning_mode": mode,
            "agent.execution_id": execution_id,
            **attributes,
        },
    ) as span:
        yield span


@contextmanager
def trace_tool_call(
    tracer: Tracer, *, tool_key: str, tool_kind: str, **attributes: object
) -> Iterator[Span]:
    """Span one tool invocation ("Tool Calls")."""
    with start_span(
        tracer,
        "agent.tool.call",
        span_type=SpanType.AUTOMATION_STEP,
        **{"agent.tool_key": tool_key, "agent.tool_kind": tool_kind, **attributes},
    ) as span:
        yield span


@contextmanager
def trace_memory_access(
    tracer: Tracer, *, agent_id: str, scope: str, operation: str, **attributes: object
) -> Iterator[Span]:
    """Span one memory read or write ("Memory Access")."""
    with start_span(
        tracer,
        "agent.memory.access",
        span_type=SpanType.DATABASE_QUERY,
        **{
            "agent.agent_id": agent_id,
            "agent.memory_scope": scope,
            "agent.memory_operation": operation,
            **attributes,
        },
    ) as span:
        yield span


@contextmanager
def trace_task_execution(
    tracer: Tracer, *, task_id: str, task_type: str, **attributes: object
) -> Iterator[Span]:
    """Span one queued task's own dispatch and execution ("Task Execution")."""
    with start_span(
        tracer,
        "agent.task.execute",
        span_type=SpanType.WORKFLOW_STEP,
        **{"agent.task_id": task_id, "agent.task_type": task_type, **attributes},
    ) as span:
        yield span


@contextmanager
def trace_approval_flow(
    tracer: Tracer, *, workflow_id: str, request_id: str, decision: str, **attributes: object
) -> Iterator[Span]:
    """Span one human-in-the-loop approval decision ("Approval Flow")."""
    with start_span(
        tracer,
        "agent.approval.flow",
        span_type=SpanType.WORKFLOW_STEP,
        **{
            "agent.workflow_id": workflow_id,
            "agent.approval_request_id": request_id,
            "agent.approval_decision": decision,
            **attributes,
        },
    ) as span:
        yield span


@contextmanager
def trace_worker_tick(
    tracer: Tracer, *, worker: str, processed: int, **attributes: object
) -> Iterator[Span]:
    """Span one background worker's sweep tick."""
    with start_span(
        tracer,
        "agent.worker.tick",
        span_type=SpanType.BACKGROUND_JOB,
        **{"agent.worker": worker, "agent.processed": processed, **attributes},
    ) as span:
        yield span


__all__ = [
    "trace_ai_request",
    "trace_approval_flow",
    "trace_memory_access",
    "trace_model_inference",
    "trace_planning",
    "trace_reasoning",
    "trace_task_execution",
    "trace_tool_call",
    "trace_worker_tick",
]
