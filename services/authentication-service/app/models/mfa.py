"""``mfa_devices`` table.

Per docs/030 "MULTI-FACTOR AUTHENTICATION": TOTP, Recovery Codes,
Backup Codes. Recovery codes are stored as a JSON array of hashed
codes on the owning TOTP device row rather than as their own table,
since docs/030 "DATABASE TABLES" names only ``mfa_devices``. "Trusted
Devices" (skip MFA on a device already vouched for) is a
:mod:`app.models.device` concept, not a device *type* here -- a
trusted device has no TOTP secret or recovery codes of its own.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import MfaDeviceType


class MfaDevice(BaseModel):
    """One registered TOTP second factor, with its hashed recovery codes."""

    __tablename__ = "mfa_devices"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    device_type: Mapped[MfaDeviceType] = mapped_column(String(32), default=MfaDeviceType.TOTP)
    secret: Mapped[str] = mapped_column(String(255))
    recovery_codes_hashed: Mapped[list[str] | None] = mapped_column(JSON, default=None)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["MfaDevice"]
