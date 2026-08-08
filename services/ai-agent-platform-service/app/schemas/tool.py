"""Request/response shapes for ``/agents/tools`` (docs/060 "REST APIs")."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import PermissionCategory, ToolKind


class ToolRegisterRequest(BaseModel):
    """``POST /agents/tools``."""

    tool_key: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=128)
    tool_kind: ToolKind
    description: str | None = None
    category: str = "general"
    parameters_schema: dict[str, Any] = Field(default_factory=dict)
    required_permission: PermissionCategory = PermissionCategory.TOOL_INVOCATION
    is_mutating: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolResponse(BaseModel):
    """One registered tool."""

    id: UUID
    organization_id: UUID
    tool_key: str
    name: str
    description: str | None
    tool_kind: ToolKind
    category: str
    parameters_schema: dict[str, Any]
    required_permission: PermissionCategory
    is_mutating: bool
    version_number: str
    enabled: bool
    is_deprecated: bool
    health_status: str
    created_at: datetime

    model_config = {"from_attributes": True}


__all__ = ["ToolRegisterRequest", "ToolResponse"]
