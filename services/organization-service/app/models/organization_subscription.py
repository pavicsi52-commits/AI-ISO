"""``organization_subscriptions`` table. Per docs/033 "SUBSCRIPTIONS":
Track Renewal, Expiration, Billing Reference, Status.
"""

from __future__ import annotations

from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import SubscriptionPlan, SubscriptionStatus


class OrganizationSubscription(BaseModel):
    """One organization's current subscription plan."""

    __tablename__ = "organization_subscriptions"
    __table_args__ = (
        ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        UniqueConstraint("organization_id", name="uq_organization_subscription_org"),
    )

    plan: Mapped[SubscriptionPlan] = mapped_column(String(16), default=SubscriptionPlan.TRIAL)
    status: Mapped[SubscriptionStatus] = mapped_column(
        String(16), default=SubscriptionStatus.ACTIVE
    )
    billing_reference: Mapped[str | None] = mapped_column(String(255), default=None)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    renews_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["OrganizationSubscription"]
