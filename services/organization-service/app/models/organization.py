"""``organizations`` table -- the tenant root entity.

Per docs/033 "ORGANIZATION MODEL": Organization ID, Name, Display Name,
Short Name, Description, Status, Primary Domain, Primary Contact,
Logo, Website, Industry, Timezone, Language, Country, Currency,
Subscription, License, Metadata. "Subscription"/"License" are relations
(:class:`~app.models.organization_subscription.OrganizationSubscription`/
:class:`~app.models.organization_license.OrganizationLicense`), not
columns here -- every AI-IOS entity so far has kept one-to-one relation
data in its own table rather than an ever-growing parent row (the same
choice ``services/user-management-service`` made for
profile/preferences/settings).
"""

from __future__ import annotations

from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import OrganizationStatus


class Organization(BaseModel):
    """One tenant. Its own ``organization_id`` column equals its own ``id``."""

    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str | None] = mapped_column(String(255), default=None)
    short_name: Mapped[str | None] = mapped_column(String(64), default=None)
    slug: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(String(2048), default=None)
    status: Mapped[OrganizationStatus] = mapped_column(
        String(16), default=OrganizationStatus.PENDING, index=True
    )
    primary_domain: Mapped[str | None] = mapped_column(String(255), default=None)
    primary_contact_email: Mapped[str | None] = mapped_column(String(255), default=None)
    logo_url: Mapped[str | None] = mapped_column(String(1024), default=None)
    website: Mapped[str | None] = mapped_column(String(1024), default=None)
    industry: Mapped[str | None] = mapped_column(String(128), default=None)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    language: Mapped[str] = mapped_column(String(16), default="en")
    country: Mapped[str | None] = mapped_column(String(2), default=None)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)


__all__ = ["Organization"]
