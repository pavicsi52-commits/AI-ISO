"""``organization_licenses`` table. Per docs/033 "LICENSE MANAGEMENT":
License Type, License Key, Seat Count, Consumed Seats, Expiration,
Grace Period, Activation, Validation.
"""

from __future__ import annotations

from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, ForeignKeyConstraint, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import LicenseStatus


class OrganizationLicense(BaseModel):
    """One organization's current license."""

    __tablename__ = "organization_licenses"
    __table_args__ = (
        ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        UniqueConstraint("organization_id", name="uq_organization_license_org"),
    )

    license_type: Mapped[str] = mapped_column(String(64), default="standard")
    license_key: Mapped[str] = mapped_column(String(255), unique=True)
    seat_count: Mapped[int] = mapped_column(Integer, default=1)
    consumed_seats: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[LicenseStatus] = mapped_column(
        String(20), default=LicenseStatus.PENDING_ACTIVATION
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    grace_period_days: Mapped[int] = mapped_column(Integer, default=14)


__all__ = ["OrganizationLicense"]
