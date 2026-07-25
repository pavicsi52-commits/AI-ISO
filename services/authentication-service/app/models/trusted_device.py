"""``trusted_devices`` table.

Per docs/030 "DEVICE MANAGEMENT": Device ID, Browser, Operating
System, IP Address, Location, Last Login, Trusted Status, Device
Revocation.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column


class TrustedDevice(BaseModel):
    """One device a user has logged in from, optionally marked trusted."""

    __tablename__ = "trusted_devices"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    device_fingerprint: Mapped[str] = mapped_column(String(128), index=True)
    device_name: Mapped[str | None] = mapped_column(String(255), default=None)
    browser: Mapped[str | None] = mapped_column(String(128), default=None)
    operating_system: Mapped[str | None] = mapped_column(String(128), default=None)
    ip_address: Mapped[str | None] = mapped_column(String(64), default=None)
    location: Mapped[str | None] = mapped_column(String(255), default=None)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    is_trusted: Mapped[bool] = mapped_column(Boolean, default=False)
    trusted_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["TrustedDevice"]
