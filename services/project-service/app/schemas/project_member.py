"""Request/response schemas for ``/projects/{id}/members``."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import ProjectMemberStatus


class AddMemberRequest(BaseModel):
    """Body of ``POST /projects/{id}/members``."""

    user_id: UUID
    role_code: str


class UpdateMemberRoleRequest(BaseModel):
    """Body of ``PUT /projects/{id}/members/{memberId}/roles``."""

    role_code: str


class ProjectMemberResponse(BaseModel):
    """One project membership, in full."""

    id: UUID
    project_id: UUID
    user_id: UUID
    role_id: UUID
    role_code: str
    role_name: str
    status: ProjectMemberStatus
    invited_by: UUID | None
    created_at: datetime


__all__ = ["AddMemberRequest", "ProjectMemberResponse", "UpdateMemberRoleRequest"]
