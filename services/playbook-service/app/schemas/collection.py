"""Request/response schemas for playbook Ansible collection references."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class PlaybookCollectionCreateRequest(BaseModel):
    """Body of ``POST /playbooks/{id}/collections``."""

    collection_name: str = Field(min_length=1, max_length=255)
    collection_version: str | None = Field(default=None, max_length=64)
    source: str | None = Field(default=None, max_length=255)


class PlaybookCollectionResponse(BaseModel):
    """One Ansible collection a playbook references."""

    id: UUID
    playbook_id: UUID
    collection_name: str
    collection_version: str | None
    source: str | None


__all__ = ["PlaybookCollectionCreateRequest", "PlaybookCollectionResponse"]
