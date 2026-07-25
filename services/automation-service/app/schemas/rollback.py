"""Request/response schemas for automation execution rollbacks."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import RollbackStatus, RollbackType


class AutomationRollbackCreateRequest(BaseModel):
    """Body of ``POST /automation/executions/{id}/rollback``."""

    rollback_type: RollbackType = RollbackType.MANUAL
    initiated_by: UUID | None = None
    reason: str | None = Field(default=None, max_length=1024)


class AutomationRollbackResponse(BaseModel):
    """One rollback operation against an automation execution."""

    id: UUID
    execution_id: UUID
    rollback_type: RollbackType
    status: RollbackStatus
    initiated_by: UUID | None
    reason: str | None
    completed_at: datetime | None


__all__ = ["AutomationRollbackCreateRequest", "AutomationRollbackResponse"]
