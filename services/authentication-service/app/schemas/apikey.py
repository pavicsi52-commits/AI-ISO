"""Request/response schemas for POST/GET/DELETE /auth/apikeys."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ApiKeyCreateRequest(BaseModel):
    """Body of ``POST /auth/apikeys``."""

    name: str = Field(max_length=255)
    scopes: list[str] = Field(default_factory=list)
    expires_in_days: int | None = Field(default=None, ge=1)


class ApiKeyCreatedResponse(BaseModel):
    """Returned once, immediately after creation -- the raw key is never retrievable again."""

    id: UUID
    name: str
    key_prefix: str
    raw_key: str
    scopes: list[str]
    expires_at: datetime | None


class ApiKeySummary(BaseModel):
    """One API key, as returned by ``GET /auth/apikeys`` (never includes the raw key)."""

    id: UUID
    name: str
    key_prefix: str
    scopes: list[str]
    expires_at: datetime | None
    last_used_at: datetime | None
    revoked_at: datetime | None


__all__ = ["ApiKeyCreateRequest", "ApiKeyCreatedResponse", "ApiKeySummary"]
