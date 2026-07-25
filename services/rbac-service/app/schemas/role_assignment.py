"""Request/response schemas for ``/users/{id}/roles`` and ``/users/{id}/permissions``.

Per docs/032 "ROLE HIERARCHY"/"ORGANIZATION ROLES"/"PROJECT ROLES": one
role can be assigned to a user at the system, organization, or project
scope -- ``scope_type``/``scope_id`` route the request to
``user_roles``/``organization_roles``/``project_roles`` respectively
(see :class:`app.services.role_assignment.RoleAssignmentService`),
rather than exposing three separate REST surfaces docs/032's own
endpoint list doesn't name.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.models.enums import AssignmentStatus, SubjectType


class AssignRoleRequest(BaseModel):
    """Body of ``POST /users/{id}/roles``."""

    role_id: UUID
    scope_type: SubjectType = SubjectType.GLOBAL
    scope_id: UUID | None = None
    expires_at: datetime | None = None

    @model_validator(mode="after")
    def _validate_scope(self) -> AssignRoleRequest:
        if self.scope_type in (SubjectType.ORGANIZATION, SubjectType.PROJECT) and (
            self.scope_id is None
        ):
            raise ValueError(f"scope_id is required when scope_type is {self.scope_type!r}.")
        return self


class RoleAssignmentResponse(BaseModel):
    """One role assignment, regardless of which scope table it lives in."""

    id: UUID
    user_id: UUID
    role_id: UUID
    scope_type: SubjectType
    scope_id: UUID | None
    status: AssignmentStatus
    assigned_by: UUID | None
    expires_at: datetime | None
    created_at: datetime


class UserPermissionsResponse(BaseModel):
    """A user's aggregated effective permissions ("Permission Aggregation")."""

    user_id: UUID
    organization_id: UUID | None = None
    project_id: UUID | None = None
    permissions: list[str] = Field(default_factory=list)
    role_codes: list[str] = Field(default_factory=list)
    computed_at: datetime


__all__ = ["AssignRoleRequest", "RoleAssignmentResponse", "UserPermissionsResponse"]
