"""``api_keys`` and ``api_key_permissions``.

Persists `shared_core.security.apikey.ApiKeyRecord` (Prompt 017) --
this table is the durable store behind that framework's otherwise
stateless generate/hash/rotate/revoke functions, per this prompt's own
"use every previously implemented platform framework" instruction.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ApiKeyStatus


class ApiKey(BaseModel):
    """``api_keys`` -- one issued API key."""

    __tablename__ = "api_keys"
    __table_args__ = (Index("ix_api_key_org_client", "organization_id", "client_id"),)

    client_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("api_clients.id", ondelete="CASCADE"), index=True
    )
    key_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    hashed_key: Mapped[str] = mapped_column(String(128))
    name: Mapped[str] = mapped_column(String(128))

    scopes: Mapped[list[str]] = mapped_column(JSON, default=list)
    ip_allowlist: Mapped[list[str]] = mapped_column(JSON, default=list)

    status: Mapped[ApiKeyStatus] = mapped_column(
        String(16), default=ApiKeyStatus.ACTIVE, index=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class ApiKeyPermission(BaseModel):
    """``api_key_permissions`` -- one fine-grained grant beyond a key's own scopes."""

    __tablename__ = "api_key_permissions"
    __table_args__ = (Index("ix_api_key_permission_key", "organization_id", "api_key_id"),)

    api_key_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("api_keys.id", ondelete="CASCADE"), index=True
    )
    resource: Mapped[str] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(64))


__all__ = ["ApiKey", "ApiKeyPermission"]
