"""Request/response schemas for configuration variables."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import VariableScope


class ConfigurationVariableCreateRequest(BaseModel):
    """Body of ``POST /configurations/variables``."""

    organization_id: UUID
    project_id: UUID | None = None
    scope: VariableScope
    scope_ref_id: UUID | None = None
    key: str = Field(min_length=1, max_length=255)
    value: str | None = Field(default=None, max_length=4096)
    is_secret_reference: bool = False
    is_computed: bool = False
    validation_rule: dict[str, Any] | None = None


class ConfigurationVariableUpdateRequest(BaseModel):
    """Body of ``PUT /configurations/variables/{id}``."""

    value: str | None = Field(default=None, max_length=4096)
    is_secret_reference: bool = False
    is_computed: bool = False
    validation_rule: dict[str, Any] | None = None


class ConfigurationVariableResponse(BaseModel):
    """One scoped configuration variable."""

    id: UUID
    organization_id: UUID
    project_id: UUID | None
    scope: VariableScope
    scope_ref_id: UUID | None
    key: str
    value: str | None
    is_secret_reference: bool
    is_computed: bool
    validation_rule: dict[str, Any] | None


__all__ = [
    "ConfigurationVariableCreateRequest",
    "ConfigurationVariableResponse",
    "ConfigurationVariableUpdateRequest",
]
