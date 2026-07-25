"""Request/response schemas for ``/organizations/{id}/departments`` and ``/departments/{id}``."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class DepartmentCreateRequest(BaseModel):
    """Body of ``POST /organizations/{id}/departments``."""

    name: str = Field(min_length=1, max_length=255)
    code: str = Field(min_length=1, max_length=64)
    description: str | None = None
    parent_department_id: UUID | None = None
    manager_id: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DepartmentUpdateRequest(BaseModel):
    """Body of ``PUT /departments/{id}``."""

    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    parent_department_id: UUID | None = None
    manager_id: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DepartmentResponse(BaseModel):
    """One department, in full."""

    id: UUID
    organization_id: UUID
    name: str
    code: str
    description: str | None
    parent_department_id: UUID | None
    manager_id: UUID | None
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


__all__ = ["DepartmentCreateRequest", "DepartmentResponse", "DepartmentUpdateRequest"]
