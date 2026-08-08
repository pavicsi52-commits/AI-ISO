"""Tests for :mod:`app.telemetry.tracing`.

**Recorded with the real OpenTelemetry SDK, never a mock tracer.** Each
test drives a genuine ``opentelemetry.sdk.trace.TracerProvider`` with a
``SimpleSpanProcessor`` feeding an ``InMemorySpanExporter``, so every
assertion is made against a span the SDK itself actually built,
finished, and exported.

That matters for more than realism here: this module's own docstring
warns that ``start_span``'s signature is
``start_span(tracer, name, *, span_type=None, **attributes)`` -- passing
``attributes={...}`` silently drops every attribute instead of raising.
A recording tracer is the only thing that can *prove* the ``**{...}``
unpacking these helpers use genuinely lands the attributes on the span;
a mock would happily report success either way.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import NoOpTracer, Tracer
from shared_core.telemetry.constants import MASKED_ATTRIBUTE_VALUE
from shared_core.telemetry.span import SpanType

from app.telemetry.tracing import (
    trace_ai_request,
    trace_approval_flow,
    trace_memory_access,
    trace_model_inference,
    trace_planning,
    trace_reasoning,
    trace_task_execution,
    trace_tool_call,
    trace_worker_tick,
)


class SpanRecorder:
    """A real in-process OTel pipeline: provider -> processor -> exporter."""

    def __init__(self) -> None:
        self.exporter = InMemorySpanExporter()
        self._provider = TracerProvider()
        self._provider.add_span_processor(SimpleSpanProcessor(self.exporter))
        self.tracer: Tracer = self._provider.get_tracer("tests.app.telemetry")

    @property
    def spans(self) -> tuple[ReadableSpan, ...]:
        """Every span finished so far, in completion order."""
        return self.exporter.get_finished_spans()

    def only(self) -> ReadableSpan:
        """The single span this recorder captured."""
        finished = self.spans
        assert len(finished) == 1, f"expected exactly one span, got {len(finished)}"
        return finished[0]

    def attributes(self) -> dict[str, Any]:
        """The single captured span's own attributes, as a plain dict."""
        return dict(self.only().attributes or {})

    def shutdown(self) -> None:
        self._provider.shutdown()


@pytest.fixture
def recorder() -> Iterator[SpanRecorder]:
    span_recorder = SpanRecorder()
    try:
        yield span_recorder
    finally:
        span_recorder.shutdown()


# ---- trace_planning ------------------------------------------------------------


def test_trace_planning_records_name_type_and_attributes(recorder: SpanRecorder) -> None:
    with trace_planning(recorder.tracer, agent_id="agent-1", mode="chain_of_thought") as span:
        assert span.is_recording()

    finished = recorder.only()
    assert finished.name == "agent.planning"
    assert recorder.attributes() == {
        "agent.agent_id": "agent-1",
        "agent.reasoning_mode": "chain_of_thought",
        "span.type": SpanType.WORKFLOW_STEP.value,
    }


def test_trace_planning_ends_the_span_on_exit(recorder: SpanRecorder) -> None:
    with trace_planning(recorder.tracer, agent_id="agent-1", mode="reflection"):
        assert recorder.spans == ()

    assert recorder.only().end_time is not None


def test_trace_planning_carries_extra_attributes(recorder: SpanRecorder) -> None:
    with trace_planning(
        recorder.tracer, agent_id="agent-1", mode="hybrid", **{"agent.plan_steps": 4}
    ):
        pass

    assert recorder.attributes()["agent.plan_steps"] == 4


# ---- trace_reasoning -----------------------------------------------------------


def test_trace_reasoning_records_execution_id(recorder: SpanRecorder) -> None:
    with trace_reasoning(
        recorder.tracer, agent_id="agent-2", mode="tool_based", execution_id="exec-9"
    ):
        pass

    assert recorder.only().name == "agent.reasoning"
    assert recorder.attributes() == {
        "agent.agent_id": "agent-2",
        "agent.reasoning_mode": "tool_based",
        "agent.execution_id": "exec-9",
        "span.type": SpanType.WORKFLOW_STEP.value,
    }


def test_trace_reasoning_extra_attribute_can_override_a_default(recorder: SpanRecorder) -> None:
    """``**{defaults, **attributes}`` puts caller attributes last, so a
    caller-supplied key of the same name genuinely wins."""
    with trace_reasoning(
        recorder.tracer,
        agent_id="agent-2",
        mode="tool_based",
        execution_id="exec-9",
        **{"agent.reasoning_mode": "overridden"},
    ):
        pass

    assert recorder.attributes()["agent.reasoning_mode"] == "overridden"


# ---- trace_tool_call -----------------------------------------------------------


def test_trace_tool_call_uses_the_automation_step_span_type(recorder: SpanRecorder) -> None:
    with trace_tool_call(recorder.tracer, tool_key="crm.lookup", tool_kind="rest"):
        pass

    assert recorder.only().name == "agent.tool.call"
    assert recorder.attributes() == {
        "agent.tool_key": "crm.lookup",
        "agent.tool_kind": "rest",
        "span.type": SpanType.AUTOMATION_STEP.value,
    }


def test_trace_tool_call_masks_a_sensitive_extra_attribute(recorder: SpanRecorder) -> None:
    """``start_span`` sanitises by attribute *name*; ``tool_key`` is not
    one of the sensitive keywords but ``api_key`` is."""
    with trace_tool_call(
        recorder.tracer, tool_key="crm.lookup", tool_kind="rest", api_key="super-secret"
    ):
        pass

    attributes = recorder.attributes()
    assert attributes["api_key"] == MASKED_ATTRIBUTE_VALUE
    assert attributes["agent.tool_key"] == "crm.lookup"


# ---- trace_memory_access -------------------------------------------------------


def test_trace_memory_access_uses_the_database_query_span_type(recorder: SpanRecorder) -> None:
    with trace_memory_access(
        recorder.tracer, agent_id="agent-3", scope="long_term", operation="write"
    ):
        pass

    assert recorder.only().name == "agent.memory.access"
    assert recorder.attributes() == {
        "agent.agent_id": "agent-3",
        "agent.memory_scope": "long_term",
        "agent.memory_operation": "write",
        "span.type": SpanType.DATABASE_QUERY.value,
    }


# ---- trace_task_execution ------------------------------------------------------


def test_trace_task_execution_records_task_identity(recorder: SpanRecorder) -> None:
    with trace_task_execution(recorder.tracer, task_id="task-7", task_type="report"):
        pass

    assert recorder.only().name == "agent.task.execute"
    assert recorder.attributes() == {
        "agent.task_id": "task-7",
        "agent.task_type": "report",
        "span.type": SpanType.WORKFLOW_STEP.value,
    }


# ---- trace_approval_flow -------------------------------------------------------


def test_trace_approval_flow_records_the_decision(recorder: SpanRecorder) -> None:
    with trace_approval_flow(
        recorder.tracer, workflow_id="wf-1", request_id="wf-1:gate", decision="approved"
    ):
        pass

    assert recorder.only().name == "agent.approval.flow"
    assert recorder.attributes() == {
        "agent.workflow_id": "wf-1",
        "agent.approval_request_id": "wf-1:gate",
        "agent.approval_decision": "approved",
        "span.type": SpanType.WORKFLOW_STEP.value,
    }


# ---- trace_worker_tick ---------------------------------------------------------


def test_trace_worker_tick_records_an_integer_attribute(recorder: SpanRecorder) -> None:
    with trace_worker_tick(recorder.tracer, worker="task-dispatch-sweep", processed=12):
        pass

    assert recorder.only().name == "agent.worker.tick"
    attributes = recorder.attributes()
    assert attributes == {
        "agent.worker": "task-dispatch-sweep",
        "agent.processed": 12,
        "span.type": SpanType.BACKGROUND_JOB.value,
    }
    assert isinstance(attributes["agent.processed"], int)


def test_trace_worker_tick_records_zero_processed(recorder: SpanRecorder) -> None:
    """``0`` is a real, meaningful tick result -- it must not be dropped
    as falsy."""
    with trace_worker_tick(recorder.tracer, worker="benchmark-sweep", processed=0):
        pass

    assert recorder.attributes()["agent.processed"] == 0


# ---- re-exported shared_core AI spans -------------------------------------------


def test_trace_ai_request_is_the_shared_core_helper(recorder: SpanRecorder) -> None:
    with trace_ai_request(recorder.tracer, "ollama", model_name="llama3"):
        pass

    assert recorder.only().name == "ai.request ollama"
    assert recorder.attributes() == {
        "provider": "ollama",
        "model_name": "llama3",
        "span.type": SpanType.AI_REQUEST.value,
    }


def test_trace_model_inference_is_the_shared_core_helper(recorder: SpanRecorder) -> None:
    with trace_model_inference(recorder.tracer, "llama3", provider="ollama"):
        pass

    assert recorder.only().name == "ai.inference llama3"
    assert recorder.attributes() == {
        "model_name": "llama3",
        "provider": "ollama",
        "span.type": SpanType.MODEL_INFERENCE.value,
    }


# ---- nesting, exceptions, and degenerate tracers ----------------------------------


def test_nested_helpers_attach_to_the_enclosing_span(recorder: SpanRecorder) -> None:
    """``start_span`` uses ``start_as_current_span``, so a helper opened
    inside another is genuinely its child in the same trace."""
    # A combined `with` still nests the contexts in order, so the
    # parent/child relationship this test is about is unchanged.
    with (
        trace_task_execution(recorder.tracer, task_id="task-7", task_type="report"),
        trace_tool_call(recorder.tracer, tool_key="crm.lookup", tool_kind="rest"),
    ):
        pass

    child, parent = recorder.spans
    assert child.name == "agent.tool.call"
    assert parent.name == "agent.task.execute"
    assert child.parent is not None
    assert child.parent.span_id == parent.context.span_id
    assert child.context.trace_id == parent.context.trace_id


def test_an_exception_inside_the_block_still_ends_the_span(recorder: SpanRecorder) -> None:
    with (
        pytest.raises(RuntimeError, match="boom"),
        trace_reasoning(
            recorder.tracer, agent_id="agent-4", mode="reflection", execution_id="exec-4"
        ),
    ):
        raise RuntimeError("boom")

    finished = recorder.only()
    assert finished.end_time is not None
    assert finished.attributes is not None
    assert finished.attributes["agent.agent_id"] == "agent-4"
    assert len(finished.events) == 1
    assert finished.events[0].name == "exception"


def test_helpers_are_no_ops_against_a_noop_tracer() -> None:
    """``NoOpTracer`` is a real OTel type used when no provider is
    configured: the helpers must still yield a usable, non-recording
    span rather than raising."""
    tracer = NoOpTracer()

    with trace_worker_tick(tracer, worker="statistics-rollup", processed=3) as span:
        span.set_attribute("extra", "value")
        assert not span.is_recording()


def test_a_none_tracer_raises_on_entry() -> None:
    """``start_span`` calls ``tracer.start_as_current_span`` directly, so
    ``None`` is not a supported "tracing disabled" sentinel -- it fails
    loudly at ``__enter__``, which is the real behaviour callers must
    code against."""
    manager = trace_planning(None, agent_id="agent-5", mode="hybrid")  # type: ignore[arg-type]

    with pytest.raises(AttributeError, match="start_as_current_span"):
        manager.__enter__()
