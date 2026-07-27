"""Request/response schemas for ``/playbooks/templates``."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import ContentType


class PlaybookTemplateCreateRequest(BaseModel):
    """Body of ``POST /playbooks/templates``."""

    organization_id: UUID
    template_name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    content_type: ContentType
    content: str = Field(min_length=1)
    variables_schema: dict[str, Any] = Field(default_factory=dict)


class PlaybookTemplateResponse(BaseModel):
    """One reusable automation content template."""

    id: UUID
    organization_id: UUID
    template_name: str
    description: str | None
    content_type: ContentType
    content: str
    variables_schema: dict[str, Any]


__all__ = ["PlaybookTemplateCreateRequest", "PlaybookTemplateResponse"]
