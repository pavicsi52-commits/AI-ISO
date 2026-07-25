"""``login_history`` table.

Per docs/030 "LOGIN"/"AUDIT": Every Login. Append-only; ``created_at``
(from :class:`~shared_core.base.timestamp_mixin.TimestampMixin`) *is*
the event timestamp, so no separate ``occurred_at`` column is added.
"""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import AuthMethod


class LoginHistoryEntry(BaseModel):
    """One successful login."""

    __tablename__ = "login_history"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    method: Mapped[AuthMethod] = mapped_column(String(32))
    ip_address: Mapped[str | None] = mapped_column(String(64), default=None)
    user_agent: Mapped[str | None] = mapped_column(String(512), default=None)
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("trusted_devices.id"), default=None
    )


__all__ = ["LoginHistoryEntry"]
