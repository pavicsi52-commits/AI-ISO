"""Request/response schemas for ``/secrets``.

**Design resolution**: docs/035's REST list has no separate "reveal"
endpoint, and its own OBJECTIVE states other services retrieve
credentials via this API -- so ``GET /secrets/{id}``
(:class:`SecretDetailResponse`) includes the decrypted current value.
List/search views (:class:`SecretSummaryResponse`, used by
``GET /secrets`` and ``GET /secrets/search``) never do, matching
docs/035's own "PERFORMANCE" section: "Never cache decrypted secrets"
and "Caching of metadata only" -- a list response is exactly the kind
of thing a cache or log line might capture in bulk.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import SecretStatus, SecretType


class SecretCreateRequest(BaseModel):
    """Body of ``POST /secrets``."""

    organization_id: UUID
    project_id: UUID | None = None
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    category_id: UUID | None = None
    secret_type: SecretType
    owner_id: UUID
    value: str = Field(min_length=1)
    expires_at: datetime | None = None
    rotation_policy: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class SecretUpdateRequest(BaseModel):
    """Body of ``PUT /secrets/{id}``.

    Updates identity/lifecycle fields only -- changing the secret's
    *value* is exclusively done through ``POST /secrets/{id}/rotate``,
    which also records rotation history.
    """

    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    category_id: UUID | None = None
    status: SecretStatus = SecretStatus.ACTIVE
    expires_at: datetime | None = None
    rotation_policy: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SecretRotateRequest(BaseModel):
    """Body of ``POST /secrets/{id}/rotate`` ("Manual Rotation")."""

    new_value: str = Field(min_length=1)


class SecretSummaryResponse(BaseModel):
    """One secret's identity and lifecycle -- never its value. Used by
    list and search views.
    """

    id: UUID
    organization_id: UUID
    project_id: UUID | None
    name: str
    description: str | None
    category_id: UUID | None
    secret_type: SecretType
    status: SecretStatus
    owner_id: UUID
    current_version: int
    expires_at: datetime | None
    rotation_policy: dict[str, Any]
    metadata: dict[str, Any]
    tags: list[str]
    created_at: datetime
    updated_at: datetime


class SecretDetailResponse(SecretSummaryResponse):
    """One secret, in full, including its decrypted current value.

    Used only by ``GET /secrets/{id}`` -- see the module docstring for
    why this is the one response shape that carries plaintext.
    """

    value: str


__all__ = [
    "SecretCreateRequest",
    "SecretDetailResponse",
    "SecretRotateRequest",
    "SecretSummaryResponse",
    "SecretUpdateRequest",
]
