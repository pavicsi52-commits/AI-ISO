"""Request/response schemas for ``POST /assets/{id}/assign``."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import AssignmentStatus, AssignmentType


class AssetAssignRequest(BaseModel):
    """Body of ``POST /assets/{id}/assign``."""

    assignee_id: UUID
    assignment_type: AssignmentType = AssignmentType.STANDARD
    expires_at: datetime | None = None
    notes: str | None = None


class AssetAssignmentResponse(BaseModel):
    """One assignment record."""

    id: UUID
    managed_asset_id: UUID
    assignee_id: UUID
    assignment_type: AssignmentType
    status: AssignmentStatus
    assigned_by: UUID | None
    assigned_at: datetime
    expires_at: datetime | None
    returned_at: datetime | None
    notes: str | None


__all__ = ["AssetAssignRequest", "AssetAssignmentResponse"]
