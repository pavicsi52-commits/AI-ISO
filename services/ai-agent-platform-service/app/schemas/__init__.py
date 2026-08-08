"""Pydantic request/response schemas (docs/060 "REST APIs")."""

from __future__ import annotations

from app.schemas.agent import (
    AgentExecuteRequest,
    AgentExecutionResponse,
    AgentRegisterRequest,
    AgentResponse,
    AgentUpdateRequest,
    ProfilePayload,
)
from app.schemas.governance import (
    BenchmarkResponse,
    EvaluationResponse,
    ReportResponse,
    StatisticResponse,
)
from app.schemas.health import HealthStatus, LivenessStatus, ReadinessCheck, ReadinessStatus
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.task import TaskCreateRequest, TaskResponse
from app.schemas.tool import ToolRegisterRequest, ToolResponse

__all__ = [
    "AgentExecuteRequest",
    "AgentExecutionResponse",
    "AgentRegisterRequest",
    "AgentResponse",
    "AgentUpdateRequest",
    "BenchmarkResponse",
    "EvaluationResponse",
    "HealthStatus",
    "LivenessStatus",
    "ProfilePayload",
    "ReadinessCheck",
    "ReadinessStatus",
    "ReportResponse",
    "ResponseMeta",
    "StatisticResponse",
    "SuccessResponse",
    "TaskCreateRequest",
    "TaskResponse",
    "ToolRegisterRequest",
    "ToolResponse",
]
