"""``organization_domains`` table -- verified email domains for an organization.

Per docs/033 "ORGANIZATION SETTINGS": "Allowed Domains" -- a
one-to-many table (an organization can allow multiple domains) rather
than a single column, with a ``is_primary`` flag identifying the
"Primary Domain" named in "ORGANIZATION MODEL".
"""

from __future__ import annotations

from shared_core.database.base import BaseModel
from sqlalchemy import Boolean, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import DomainVerificationStatus


class OrganizationDomain(BaseModel):
    """One domain an organization has claimed and (optionally) verified."""

    __tablename__ = "organization_domains"
    __table_args__ = (
        ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        UniqueConstraint("domain", name="uq_organization_domain"),
    )

    domain: Mapped[str] = mapped_column(String(255), index=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    verification_status: Mapped[DomainVerificationStatus] = mapped_column(
        String(16), default=DomainVerificationStatus.PENDING
    )


__all__ = ["OrganizationDomain"]
