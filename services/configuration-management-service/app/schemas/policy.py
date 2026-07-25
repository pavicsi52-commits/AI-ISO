"""Request/response schemas for configuration governance policies."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import PolicyType


class ConfigurationPolicyCreateRequest(BaseModel):
    """Body of ``POST /configurations/policies``."""

    organization_id: UUID
    project_id: UUID | None = None
    policy_type: PolicyType
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2048)
    rule: dict[str, Any] = Field(default_factory=dict)
    enforced: bool = True


class ConfigurationPolicyUpdateRequest(BaseModel):
    """Body of ``PUT /configurations/policies/{id}``."""

    description: str | None = Field(default=None, max_length=2048)
    rule: dict[str, Any] = Field(default_factory=dict)
    enforced: bool = True


class ConfigurationPolicyResponse(BaseModel):
    """One governance policy enforced against configuration profiles."""

    id: UUID
    organization_id: UUID
    project_id: UUID | None
    policy_type: PolicyType
    name: str
    description: str | None
    rule: dict[str, Any]
    enforced: bool


__all__ = [
    "ConfigurationPolicyCreateRequest",
    "ConfigurationPolicyResponse",
    "ConfigurationPolicyUpdateRequest",
]
