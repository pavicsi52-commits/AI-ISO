"""Request/response schemas for ``POST /workflows/{id}/rollback``."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import RollbackStatus, RollbackType


class WorkflowRollbackRequest(BaseModel):
    """Body of ``POST /workflows/{id}/rollback``.

    ``node_ids`` mirrors ``shared_core.workflow.rollback
    .rollback_workflow``'s own ``node_ids`` parameter: ``None`` rolls
    back every completed node ("Workflow Rollback"), an explicit list
    rolls back only those ("Step Rollback"/"Partial Rollback").
    """

    node_ids: list[str] | None = None
    rollback_type: RollbackType = RollbackType.MANUAL


class WorkflowRollbackResponse(BaseModel):
    """The outcome of a rollback request."""

    instance_id: UUID
    rollback_type: RollbackType
    status: RollbackStatus
    compensated_node_ids: list[str] = Field(default_factory=list)


__all__ = ["WorkflowRollbackRequest", "WorkflowRollbackResponse"]
