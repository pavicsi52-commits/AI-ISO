"""``service_accounts`` table.

Per docs/030 "SERVICE ACCOUNTS": Machine Accounts, Token
Authentication, Scoped Permissions, Rotation, Audit.
"""

from __future__ import annotations

from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column


class ServiceAccount(BaseModel):
    """A machine identity, authenticated by a rotating token rather than a password."""

    __tablename__ = "service_accounts"

    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(String(1024), default=None)
    hashed_token: Mapped[str] = mapped_column(String(255), unique=True)
    scopes: Mapped[str] = mapped_column(String(1024), default="")
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["ServiceAccount"]
