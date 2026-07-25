"""Request/response schemas for automation execution plans."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class AutomationExecutionPlanCreateRequest(BaseModel):
    """Body of ``POST /automation/execution-plans``."""

    organization_id: UUID
    job_id: UUID | None = None
    name: str = Field(min_length=1, max_length=255)
    steps: list[dict[str, Any]] = Field(default_factory=list)
    approval_gates: list[dict[str, Any]] = Field(default_factory=list)
    rollback_plan: dict[str, Any] | None = None


class AutomationExecutionPlanResponse(BaseModel):
    """One reusable, ordered execution plan."""

    id: UUID
    organization_id: UUID
    job_id: UUID | None
    name: str
    steps: list[dict[str, Any]]
    approval_gates: list[dict[str, Any]]
    rollback_plan: dict[str, Any] | None


__all__ = ["AutomationExecutionPlanCreateRequest", "AutomationExecutionPlanResponse"]
