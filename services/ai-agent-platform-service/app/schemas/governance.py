"""Response shapes for ``/agents/evaluations``, ``/agents/benchmarks``,
``/agents/statistics``, ``/agents/reports`` (docs/060 "REST APIs")."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import BenchmarkStatus, ReportFormat, ReportKind, ReportStatus


class EvaluationResponse(BaseModel):
    """One scored evaluation."""

    id: UUID
    agent_id: UUID
    execution_id: UUID
    task_accuracy: float | None
    execution_quality: float | None
    reasoning_quality: float | None
    tool_success_rate: float | None
    latency_ms: float | None
    cost_usd: float | None
    human_feedback_score: float | None
    is_regression_test: bool
    notes: str | None
    evaluated_by: str | None
    evaluated_at: datetime

    model_config = {"from_attributes": True}


class BenchmarkResponse(BaseModel):
    """One benchmark suite run."""

    id: UUID
    agent_id: UUID
    name: str
    status: BenchmarkStatus
    total_cases: int
    passed_cases: int
    failed_cases: int
    score: float | None
    results: list[dict[str, Any]]
    started_at: datetime
    completed_at: datetime | None
    triggered_by: str | None
    error: str | None

    model_config = {"from_attributes": True}


class StatisticResponse(BaseModel):
    """One rolled-up activity window."""

    id: UUID
    window_start: datetime
    window_end: datetime
    active_agents: int
    task_count: int
    executions_succeeded: int
    executions_failed: int
    total_tokens: int
    average_cost_usd: float | None
    average_latency_ms: float | None
    memory_rows_created: int
    by_agent_type: dict[str, int]
    by_model_provider: dict[str, int]
    by_tool: dict[str, int]

    model_config = {"from_attributes": True}


class ReportResponse(BaseModel):
    """One generated report."""

    id: UUID
    kind: ReportKind
    report_format: ReportFormat
    title: str
    status: ReportStatus
    content: dict[str, Any]
    row_count: int | None
    generated_by: str | None
    generated_at: datetime | None
    duration_ms: float | None
    error: str | None

    model_config = {"from_attributes": True}


__all__ = ["BenchmarkResponse", "EvaluationResponse", "ReportResponse", "StatisticResponse"]
