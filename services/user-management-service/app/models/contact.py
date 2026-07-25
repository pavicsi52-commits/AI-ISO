"""``user_contacts`` table.

Secondary/additional contact channels beyond ``users.email``/
``users.phone_number`` (the primary ones).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ContactType


class UserContact(BaseModel):
    """One additional contact method belonging to a user."""

    __tablename__ = "user_contacts"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    contact_type: Mapped[ContactType] = mapped_column(String(32))
    value: Mapped[str] = mapped_column(String(320))
    label: Mapped[str | None] = mapped_column(String(64), default=None)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["UserContact"]
