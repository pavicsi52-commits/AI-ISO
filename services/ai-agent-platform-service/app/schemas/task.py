"""Request/response shapes for ``/agents/tasks`` (docs/060 "REST APIs")."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import TaskPriority, TaskStatus


class TaskCreateRequest(BaseModel):
    """``POST /agents/tasks``."""

    task_type: str = Field(min_length=1, max_length=64)
    payload: dict[str, Any] = Field(default_factory=dict)
    agent_id: UUID | None = None
    parent_task_id: UUID | None = None
    priority: TaskPriority = TaskPriority.NORMAL
    scheduled_at: datetime | None = None
    max_retries: int = Field(default=3, ge=0, le=20)
    timeout_seconds: float = Field(default=300.0, gt=0)


class TaskResponse(BaseModel):
    """One queued or completed task."""

    id: UUID
    organization_id: UUID
    agent_id: UUID | None
    parent_task_id: UUID | None
    task_type: str
    status: TaskStatus
    priority: TaskPriority
    payload: dict[str, Any]
    result: dict[str, Any] | None
    retry_count: int
    max_retries: int
    timeout_seconds: float
    scheduled_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    error: str | None
    requested_by: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


__all__ = ["TaskCreateRequest", "TaskResponse"]
