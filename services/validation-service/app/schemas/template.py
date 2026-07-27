"""Request/response schemas for ``/validation-templates``."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import ValidationProfileType


class ValidationTemplateCreateRequest(BaseModel):
    """Body of ``POST /validation-templates``."""

    organization_id: UUID
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    profile_type: ValidationProfileType
    template_content: dict[str, Any] = Field(default_factory=dict)


class ValidationTemplateResponse(BaseModel):
    """A reusable starting point for creating a new validation profile."""

    id: UUID
    organization_id: UUID
    name: str
    description: str | None
    profile_type: ValidationProfileType
    template_content: dict[str, Any]
    is_system_template: bool
    authored_by: str | None


__all__ = ["ValidationTemplateCreateRequest", "ValidationTemplateResponse"]
