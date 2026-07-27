"""Request/response schemas for playbook variables."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class PlaybookVariableCreateRequest(BaseModel):
    """Body of ``POST /playbooks/{id}/variables``."""

    name: str = Field(min_length=1, max_length=255)
    default_value: str | None = Field(default=None, max_length=2048)
    required: bool = False
    runtime: bool = False
    is_secret_reference: bool = False
    env_var_name: str | None = Field(default=None, max_length=255)
    validation_rule: dict[str, Any] | None = None
    description: str | None = None


class PlaybookVariableResponse(BaseModel):
    """One input-variable definition for a playbook."""

    id: UUID
    playbook_id: UUID
    name: str
    default_value: str | None
    required: bool
    runtime: bool
    is_secret_reference: bool
    env_var_name: str | None
    validation_rule: dict[str, Any] | None
    description: str | None


__all__ = ["PlaybookVariableCreateRequest", "PlaybookVariableResponse"]
