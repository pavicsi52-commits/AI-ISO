"""``ai_sessions`` table -- a longer-lived container grouping several
conversations for one user ("MEMORY": Session Memory). Distinct from an
authentication session: this is the assistant's own working context,
which outlives any single chat thread.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column


class AiSession(BaseModel):
    """One assistant working session for a user."""

    __tablename__ = "ai_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    label: Mapped[str | None] = mapped_column(String(255), default=None)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_active_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    is_open: Mapped[bool] = mapped_column(Boolean, default=True)


__all__ = ["AiSession"]
