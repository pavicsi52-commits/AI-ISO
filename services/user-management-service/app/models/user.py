"""``users`` table.

Per docs/031_Enterprise_User_Management_Service.md "USER MODEL". This
service's own user *profile* identity, entirely separate from
`services/authentication-service`'s ``users`` table (credentials and
login mechanics belong there, per this prompt's own "This service
SHALL NOT authenticate users"). The two correlate by sharing the same
``id`` value where a self-service signup exists, but there is no
cross-service foreign key -- exactly the same bare-UUID,
no-enforced-reference convention ``organization_id`` already uses.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import UserStatus


class User(BaseModel):
    """A platform user's profile identity."""

    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(255), default=None)
    first_name: Mapped[str | None] = mapped_column(String(100), default=None)
    middle_name: Mapped[str | None] = mapped_column(String(100), default=None)
    last_name: Mapped[str | None] = mapped_column(String(100), default=None)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    phone_number: Mapped[str | None] = mapped_column(String(32), default=None)
    avatar: Mapped[str | None] = mapped_column(String(1024), default=None)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    language: Mapped[str] = mapped_column(String(16), default="en")
    locale: Mapped[str] = mapped_column(String(16), default="en-US")
    status: Mapped[UserStatus] = mapped_column(String(32), default=UserStatus.PENDING, index=True)
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)


__all__ = ["User"]
