"""Request/response schemas for ``/providers``. Per docs/035 "SECRET
PROVIDERS": Provider Abstraction Layer.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import ProviderType


class ProviderCreateRequest(BaseModel):
    """Body of ``POST /providers``."""

    organization_id: UUID
    name: str = Field(min_length=1, max_length=255)
    provider_type: ProviderType
    config: dict[str, Any] = Field(default_factory=dict)
    connection_secret_id: UUID | None = None
    is_enabled: bool = True


class ProviderResponse(BaseModel):
    """One external (or internal) secret provider's configuration."""

    id: UUID
    organization_id: UUID
    name: str
    provider_type: ProviderType
    config: dict[str, Any]
    connection_secret_id: UUID | None
    is_enabled: bool


__all__ = ["ProviderCreateRequest", "ProviderResponse"]
