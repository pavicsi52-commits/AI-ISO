"""``sessions`` table.

Per docs/030 "SESSION MANAGEMENT". This table is the durable, listable,
auditable record of every session ("Session Audit", "GET
/auth/sessions", "DELETE /auth/sessions"); the fast, per-request
validity check on every authenticated request goes through
:class:`shared_core.security.sessions.SessionManager` (Redis) instead
of hitting this table -- see :mod:`app.services.sessions`.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column


class Session(BaseModel):
    """One user session, from creation through termination/expiry."""

    __tablename__ = "sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    session_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("trusted_devices.id"), default=None
    )
    ip_address: Mapped[str | None] = mapped_column(String(64), default=None)
    user_agent: Mapped[str | None] = mapped_column(String(512), default=None)
    last_active_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    revoked_reason: Mapped[str | None] = mapped_column(String(255), default=None)


__all__ = ["Session"]
