"""``refresh_tokens`` and ``access_tokens`` tables.

Per docs/030 "JWT": Token Rotation, Token Revocation, Token Blacklist.
JWTs themselves are never stored (they're stateless, self-contained,
and short-lived); only the ``jti`` claim plus enough metadata to answer
"has this token been revoked?" and to satisfy "Token Creation"/"Token
Revocation" audit requirements.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column


class RefreshToken(BaseModel):
    """One issued refresh token's tracking record, keyed by its JWT ``jti``."""

    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    session_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sessions.id"), default=None)
    jti: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    token_hash: Mapped[str] = mapped_column(String(255))
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    replaced_by_jti: Mapped[str | None] = mapped_column(String(64), default=None)


class AccessToken(BaseModel):
    """One issued access token's tracking record, keyed by its JWT ``jti`` ("Token Blacklist")."""

    __tablename__ = "access_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    session_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sessions.id"), default=None)
    jti: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["AccessToken", "RefreshToken"]
