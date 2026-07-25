"""``password_history`` and ``password_reset_tokens`` tables.

Per docs/030 "PASSWORD POLICY": Password History, Reuse Prevention.
Per "PASSWORD RESET": Generate Secure Reset Tokens, Expiration, Single
Use, Audit.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column


class PasswordHistoryEntry(BaseModel):
    """One previously-used password hash, kept for reuse prevention."""

    __tablename__ = "password_history"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))


class PasswordResetToken(BaseModel):
    """One single-use, expiring password reset token."""

    __tablename__ = "password_reset_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(255), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["PasswordHistoryEntry", "PasswordResetToken"]
