"""Request/response schemas for ``/api-keys``. Per docs/035 "API KEY
MANAGEMENT": Generation, Scopes, Expiration, Usage Tracking.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import ApiKeyStatus


class ApiKeyCreateRequest(BaseModel):
    """Body of ``POST /api-keys``.

    :attr:`value` is optional -- when omitted, a new key value is
    generated server-side ("Generation"); when supplied, the given
    third-party key is imported as-is.
    """

    organization_id: UUID
    project_id: UUID | None = None
    name: str = Field(min_length=1, max_length=255)
    owner_id: UUID
    scopes: list[str] = Field(default_factory=list)
    expires_at: datetime | None = None
    value: str | None = None


class ApiKeyResponse(BaseModel):
    """One managed API key's metadata -- never its value. Used by
    ``GET /api-keys``.
    """

    id: UUID
    organization_id: UUID
    project_id: UUID | None
    name: str
    key_prefix: str
    secret_id: UUID
    scopes: list[str]
    status: ApiKeyStatus
    expires_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ApiKeyCreateResponse(ApiKeyResponse):
    """The response to ``POST /api-keys`` only -- carries the key value
    once, at creation time.
    """

    value: str


__all__ = ["ApiKeyCreateRequest", "ApiKeyCreateResponse", "ApiKeyResponse"]
