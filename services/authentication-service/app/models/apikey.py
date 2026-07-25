"""``api_keys`` table.

Per docs/030 "API KEYS": Personal API Keys, Organization API Keys,
Expiration, Rotation, Scopes, Revocation, Usage Tracking.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column


class ApiKey(BaseModel):
    """One issued API key. ``user_id`` is ``None`` for an organization-level key."""

    __tablename__ = "api_keys"

    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), default=None)
    name: Mapped[str] = mapped_column(String(255))
    key_prefix: Mapped[str] = mapped_column(String(16), index=True)
    hashed_key: Mapped[str] = mapped_column(String(255), unique=True)
    scopes: Mapped[str] = mapped_column(String(1024), default="")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["ApiKey"]
