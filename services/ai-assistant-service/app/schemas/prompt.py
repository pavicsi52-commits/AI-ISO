"""Request/response schemas for prompt management."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import PromptStatus


class PromptCreateRequest(BaseModel):
    """Body of ``POST /ai/prompts``."""

    organization_id: UUID
    project_id: UUID | None = None
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    template: str = Field(min_length=1)
    variables: list[str] = Field(default_factory=list)


class PromptVersionCreateRequest(BaseModel):
    """Body of ``POST /ai/prompts/{id}/versions``."""

    template: str = Field(min_length=1)
    variables: list[str] = Field(default_factory=list)


class PromptRenderRequest(BaseModel):
    """Body of ``POST /ai/prompts/{id}/render``."""

    variables: dict[str, str] = Field(default_factory=dict)


class PromptVersionResponse(BaseModel):
    """One immutable revision of a prompt."""

    id: UUID
    prompt_id: UUID
    version_number: str
    template: str
    variables: list[str]
    status: PromptStatus
    approved_by: UUID | None
    approved_at: datetime | None


class PromptResponse(BaseModel):
    """One prompt template identity."""

    id: UUID
    organization_id: UUID
    project_id: UUID | None
    name: str
    description: str | None
    current_version_number: str
    enabled: bool


class PromptRenderResponse(BaseModel):
    """A rendered prompt."""

    prompt_id: UUID
    version_number: str
    rendered: str


__all__ = [
    "PromptCreateRequest",
    "PromptRenderRequest",
    "PromptRenderResponse",
    "PromptResponse",
    "PromptVersionCreateRequest",
    "PromptVersionResponse",
]
