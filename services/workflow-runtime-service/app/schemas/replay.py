"""Request/response schemas for ``POST /workflows/{id}/replay``."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import ReplayType


class WorkflowReplayRequest(BaseModel):
    """Body of ``POST /workflows/{id}/replay``."""

    replay_type: ReplayType = ReplayType.FULL
    checkpoint_id: UUID | None = None


class WorkflowReplayResponse(BaseModel):
    """One record of replaying a workflow instance as a new run."""

    id: UUID
    instance_id: UUID
    new_instance_id: UUID
    replay_type: ReplayType
    source_checkpoint_id: UUID | None
    requested_by: UUID | None
    requested_at: datetime
    comparison: dict[str, Any] | None


__all__ = ["WorkflowReplayRequest", "WorkflowReplayResponse"]
