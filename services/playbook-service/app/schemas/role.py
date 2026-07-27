"""Request/response schemas for playbook Ansible role references."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class PlaybookRoleCreateRequest(BaseModel):
    """Body of ``POST /playbooks/{id}/roles``."""

    role_name: str = Field(min_length=1, max_length=255)
    role_source: str = Field(default="galaxy", max_length=32)
    role_version: str | None = Field(default=None, max_length=64)


class PlaybookRoleResponse(BaseModel):
    """One Ansible role a playbook references."""

    id: UUID
    playbook_id: UUID
    role_name: str
    role_source: str
    role_version: str | None


__all__ = ["PlaybookRoleCreateRequest", "PlaybookRoleResponse"]
