"""``organization_settings`` table. Per docs/033 "ORGANIZATION SETTINGS":
Security Policies, Password Policies, MFA Enforcement, Allowed Domains,
Default Language, Default Timezone, Session Policies, Retention
Policies, Storage Policies, Notification Policies. (Branding lives in
its own :class:`~app.models.organization_branding.OrganizationBranding`
table, per that section's own dedicated table.)

Every child table in this service reuses its inherited
``organization_id`` column (per
:class:`shared_core.base.tenant_mixin.TenantMixin`) as the *real*
foreign key back to the owning :class:`~app.models.organization
.Organization` row, via an explicit ``ForeignKeyConstraint`` in
``__table_args__`` rather than a second, redundant column -- unlike
every other AI-IOS service, this one actually owns the ``organizations``
table its tenant-scope column has always conceptually pointed at, so a
real constraint is both possible and correct here.
"""

from __future__ import annotations

from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, ForeignKeyConstraint, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class OrganizationSettings(BaseModel):
    """One organization's security/session/retention/notification policy set."""

    __tablename__ = "organization_settings"
    __table_args__ = (
        ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        UniqueConstraint("organization_id", name="uq_organization_settings_org"),
    )

    password_policy: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    mfa_enforced: Mapped[bool] = mapped_column(Boolean, default=False)
    allowed_domains: Mapped[list[str]] = mapped_column(JSON, default=list)
    default_language: Mapped[str] = mapped_column(String(16), default="en")
    default_timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    session_timeout_minutes: Mapped[int] = mapped_column(Integer, default=60)
    data_retention_days: Mapped[int] = mapped_column(Integer, default=365)
    storage_policy: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    notification_policy: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


__all__ = ["OrganizationSettings"]
