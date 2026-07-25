"""Request/response schemas for ``/automation/templates``."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import PlaybookType


class AutomationTemplateCreateRequest(BaseModel):
    """Body of ``POST /automation/templates``."""

    organization_id: UUID
    project_id: UUID | None = None
    template_name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2048)
    playbook_type: PlaybookType
    content: str = Field(min_length=1)
    variables_schema: dict[str, Any] = Field(default_factory=dict)


class AutomationTemplateResponse(BaseModel):
    """One reusable automation content template."""

    id: UUID
    organization_id: UUID
    project_id: UUID | None
    template_name: str
    description: str | None
    playbook_type: PlaybookType
    content: str
    variables_schema: dict[str, Any]


__all__ = ["AutomationTemplateCreateRequest", "AutomationTemplateResponse"]
