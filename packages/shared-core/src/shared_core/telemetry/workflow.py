"""Workflow execution root trace and Workflow Step span helper.

Per docs/024_Enterprise_Telemetry_Framework.md.txt "SPAN TYPES": Workflow
Step; "MIDDLEWARE": "Automatically create root traces for" Workflow
Executions. Instruments the future Workflow SDK without that SDK
depending on telemetry itself.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry.trace import Span, Tracer

from shared_core.telemetry.span import SpanType, start_span
from shared_core.telemetry.trace import start_root_trace


@contextmanager
def trace_workflow_execution(
    tracer: Tracer, workflow_name: str, **attributes: str
) -> Iterator[Span]:
    """Start a workflow run's root trace ("Workflow Executions")."""
    with start_root_trace(
        tracer, f"workflow.{workflow_name}", workflow_name=workflow_name, **attributes
    ) as span:
        yield span


@contextmanager
def trace_workflow_step(
    tracer: Tracer, workflow_name: str, step_name: str, **attributes: str
) -> Iterator[Span]:
    """Trace one workflow step ("Workflow Step"; "PERFORMANCE PROFILING": Workflow Execution)."""
    with start_span(
        tracer,
        f"workflow.step {workflow_name}.{step_name}",
        span_type=SpanType.WORKFLOW_STEP,
        workflow_name=workflow_name,
        step_name=step_name,
        **attributes,
    ) as span:
        yield span


__all__ = ["trace_workflow_execution", "trace_workflow_step"]
