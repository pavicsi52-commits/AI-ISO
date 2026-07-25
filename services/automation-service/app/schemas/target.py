"""Request/response schemas for automation execution targets."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import ConnectorType, ExecutionTargetType


class AutomationTargetCreateRequest(BaseModel):
    """Body of ``POST /automation/targets``."""

    organization_id: UUID
    project_id: UUID | None = None
    name: str = Field(min_length=1, max_length=255)
    target_type: ExecutionTargetType
    connector_type: ConnectorType
    address: str = Field(min_length=1, max_length=512)
    port: int | None = Field(default=None, ge=1, le=65_535)
    username: str | None = Field(default=None, max_length=255)
    credential_ref: str | None = Field(default=None, max_length=255)
    inventory_asset_id: UUID | None = None
    labels: dict[str, str] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AutomationTargetResponse(BaseModel):
    """One execution target an automation job can run against."""

    id: UUID
    organization_id: UUID
    project_id: UUID | None
    name: str
    target_type: ExecutionTargetType
    connector_type: ConnectorType
    address: str
    port: int | None
    username: str | None
    inventory_asset_id: UUID | None
    labels: dict[str, str]
    tags: list[str]
    metadata: dict[str, Any]


__all__ = ["AutomationTargetCreateRequest", "AutomationTargetResponse"]
