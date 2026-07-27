"""Request/response schemas for ``/workflow-instances`` and the
``/workflows/{id}`` execution-control actions.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import WorkflowInstanceStatus, WorkflowTriggerType


class WorkflowInstanceResponse(BaseModel):
    """One execution run of a workflow version."""

    id: UUID
    organization_id: UUID
    project_id: UUID | None
    definition_id: UUID
    version_id: UUID
    parent_instance_id: UUID | None
    sdk_execution_id: str | None
    status: WorkflowInstanceStatus
    trigger_type: WorkflowTriggerType
    triggered_by: UUID | None
    started_at: datetime | None
    finished_at: datetime | None
    error_message: str | None


__all__ = ["WorkflowInstanceResponse"]
