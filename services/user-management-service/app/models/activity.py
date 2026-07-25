"""``user_activity`` table.

Per docs/031 "USER ACTIVITY". Append-only; ``created_at`` (from
:class:`~shared_core.base.timestamp_mixin.TimestampMixin`) *is* the
event timestamp, matching ``services/authentication-service``'s
``login_history`` precedent -- no separate ``occurred_at`` column.
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ActivityType


class UserActivityEntry(BaseModel):
    """One recorded user-activity event."""

    __tablename__ = "user_activity"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    activity_type: Mapped[ActivityType] = mapped_column(String(32), index=True)
    description: Mapped[str | None] = mapped_column(String(1024), default=None)
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    ip_address: Mapped[str | None] = mapped_column(String(64), default=None)


__all__ = ["UserActivityEntry"]
