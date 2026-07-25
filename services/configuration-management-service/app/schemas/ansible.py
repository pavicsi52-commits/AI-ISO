"""Request/response schemas for Ansible inventory bundles."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ConfigurationAnsibleInventoryCreateRequest(BaseModel):
    """Body of ``POST /configurations/ansible``."""

    organization_id: UUID
    project_id: UUID | None = None
    profile_id: UUID | None = None
    name: str = Field(min_length=1, max_length=255)
    inventory_content: dict[str, Any] = Field(default_factory=dict)
    host_vars: dict[str, Any] = Field(default_factory=dict)
    group_vars: dict[str, Any] = Field(default_factory=dict)
    playbooks: list[str] = Field(default_factory=list)
    roles: list[str] = Field(default_factory=list)
    collections: list[str] = Field(default_factory=list)
    vault_ref: str | None = Field(default=None, max_length=255)


class ConfigurationAnsibleInventoryResponse(BaseModel):
    """One Ansible inventory bundle backing a configuration profile."""

    id: UUID
    organization_id: UUID
    project_id: UUID | None
    profile_id: UUID | None
    name: str
    inventory_content: dict[str, Any]
    host_vars: dict[str, Any]
    group_vars: dict[str, Any]
    playbooks: list[str]
    roles: list[str]
    collections: list[str]
    vault_ref: str | None


__all__ = [
    "ConfigurationAnsibleInventoryCreateRequest",
    "ConfigurationAnsibleInventoryResponse",
]
