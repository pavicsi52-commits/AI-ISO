"""``failed_logins`` table.

Per docs/030 "ACCOUNT SECURITY": Failed Login Tracking, Progressive
Delay, Temporary Lockout, Suspicious Activity Detection. ``user_id``
is nullable -- a failed attempt against an email with no matching
account still needs to be tracked (for rate limiting/suspicious-
activity purposes) but has no user to reference.
"""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import FailedLoginReason


class FailedLoginEntry(BaseModel):
    """One failed authentication attempt."""

    __tablename__ = "failed_logins"

    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), default=None)
    identifier: Mapped[str] = mapped_column(String(320), index=True)
    reason: Mapped[FailedLoginReason] = mapped_column(String(32))
    ip_address: Mapped[str | None] = mapped_column(String(64), default=None)
    user_agent: Mapped[str | None] = mapped_column(String(512), default=None)


__all__ = ["FailedLoginEntry"]
