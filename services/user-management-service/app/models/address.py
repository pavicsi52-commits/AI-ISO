"""``user_addresses`` table."""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import AddressType


class UserAddress(BaseModel):
    """One postal address belonging to a user."""

    __tablename__ = "user_addresses"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    address_type: Mapped[AddressType] = mapped_column(String(32), default=AddressType.HOME)
    line1: Mapped[str] = mapped_column(String(255))
    line2: Mapped[str | None] = mapped_column(String(255), default=None)
    city: Mapped[str | None] = mapped_column(String(128), default=None)
    state_province: Mapped[str | None] = mapped_column(String(128), default=None)
    postal_code: Mapped[str | None] = mapped_column(String(32), default=None)
    country: Mapped[str | None] = mapped_column(String(2), default=None)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)


__all__ = ["UserAddress"]
