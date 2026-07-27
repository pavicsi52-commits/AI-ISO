"""Request/response schemas for playbook categories."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class PlaybookCategoryCreateRequest(BaseModel):
    """Body of ``POST /playbooks/categories``."""

    organization_id: UUID
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None


class PlaybookCategoryResponse(BaseModel):
    """One organizational category playbooks can be filed under."""

    id: UUID
    organization_id: UUID
    name: str
    description: str | None


__all__ = ["PlaybookCategoryCreateRequest", "PlaybookCategoryResponse"]
