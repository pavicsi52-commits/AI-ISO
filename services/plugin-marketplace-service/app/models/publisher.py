"""``plugin_publishers``."""

from __future__ import annotations

from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import PublisherType, PublisherVerificationStatus


class PluginPublisher(BaseModel):
    """``plugin_publishers`` -- a first-class publisher profile.

    Genuinely new -- no publisher-as-its-own-entity precedent exists
    anywhere in the monorepo. Integration-hub-service's own
    ``ConnectorMarketplaceEntry.publisher`` is a bare display string;
    this table backs it with a real profile, verification state, and
    trust/signing-key material used to decide whether a plugin package's
    signature comes from a trusted source.
    """

    __tablename__ = "plugin_publishers"
    __table_args__ = (UniqueConstraint("organization_id", "slug", name="uq_plugin_publisher_slug"),)

    slug: Mapped[str] = mapped_column(String(64), index=True)
    display_name: Mapped[str] = mapped_column(String(128))
    publisher_type: Mapped[PublisherType] = mapped_column(
        String(16), default=PublisherType.INDIVIDUAL
    )
    contact_email: Mapped[str | None] = mapped_column(String(255), default=None)
    website_url: Mapped[str | None] = mapped_column(String(2048), default=None)
    verification_status: Mapped[PublisherVerificationStatus] = mapped_column(
        String(16), default=PublisherVerificationStatus.UNVERIFIED, index=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    verified_by: Mapped[str | None] = mapped_column(String(128), default=None)
    trusted_signing_key_fingerprint: Mapped[str | None] = mapped_column(String(128), default=None)
    """The Ed25519 public-key fingerprint (``"SHA256:<base64>"``, matching
    ``playbook-service``'s own ``compute_fingerprint`` format) this
    publisher's packages are expected to be signed with. A package whose
    signer fingerprint doesn't match is flagged, not silently trusted."""
    published_plugin_count: Mapped[int] = mapped_column(Integer, default=0)
    bio: Mapped[str | None] = mapped_column(Text, default=None)


__all__ = ["PluginPublisher"]
