"""Publisher profile management and trust (docs/059 "PUBLISHERS")."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from shared_core.exceptions.validation import ValidationError

from app.models.enums import PublisherType, PublisherVerificationStatus
from app.models.publisher import PluginPublisher
from app.repositories.publisher import PluginPublisherRepository
from app.security.signer import compute_fingerprint


class PluginPublisherService:
    """Registers a publisher profile, verifies it, and manages its trusted signing key."""

    def __init__(self, publishers: PluginPublisherRepository) -> None:
        self._publishers = publishers

    async def register(
        self,
        organization_id: UUID,
        *,
        slug: str,
        display_name: str,
        publisher_type: PublisherType = PublisherType.INDIVIDUAL,
        contact_email: str | None = None,
        website_url: str | None = None,
        bio: str | None = None,
    ) -> PluginPublisher:
        """Register a new publisher profile.

        Raises:
            ValidationError: If *slug* is already registered in this organization.
        """
        if await self._publishers.get_by_slug(organization_id, slug) is not None:
            raise ValidationError(f"A publisher with slug {slug!r} is already registered.")
        return await self._publishers.create(
            PluginPublisher(
                organization_id=organization_id,
                slug=slug,
                display_name=display_name,
                publisher_type=publisher_type,
                contact_email=contact_email,
                website_url=website_url,
                bio=bio,
                verification_status=PublisherVerificationStatus.UNVERIFIED,
            )
        )

    async def get(self, organization_id: UUID, publisher_id: UUID) -> PluginPublisher:
        """One publisher.

        Raises:
            NotFoundError: If it does not exist here.
        """
        return await self._publishers.require_in_org(organization_id, publisher_id)

    async def list_for_org(self, organization_id: UUID) -> list[PluginPublisher]:
        """Every publisher profile registered in this organization."""
        return await self._publishers.list_for_org(organization_id)

    async def request_verification(
        self, organization_id: UUID, publisher_id: UUID
    ) -> PluginPublisher:
        """Move a publisher into ``PENDING`` verification."""
        publisher = await self.get(organization_id, publisher_id)
        publisher.verification_status = PublisherVerificationStatus.PENDING
        return await self._publishers.update(publisher)

    async def verify(
        self, organization_id: UUID, publisher_id: UUID, *, verified_by: str | None = None
    ) -> PluginPublisher:
        """Mark a publisher verified."""
        publisher = await self.get(organization_id, publisher_id)
        publisher.verification_status = PublisherVerificationStatus.VERIFIED
        publisher.verified_at = datetime.now(UTC)
        publisher.verified_by = verified_by
        return await self._publishers.update(publisher)

    async def revoke_verification(
        self, organization_id: UUID, publisher_id: UUID
    ) -> PluginPublisher:
        """Revoke a publisher's own verified status."""
        publisher = await self.get(organization_id, publisher_id)
        publisher.verification_status = PublisherVerificationStatus.REVOKED
        return await self._publishers.update(publisher)

    async def set_trusted_signing_key(
        self, organization_id: UUID, publisher_id: UUID, *, public_key_pem: str
    ) -> PluginPublisher:
        """Register the Ed25519 public key this publisher's packages are
        expected to be signed with.
        """
        publisher = await self.get(organization_id, publisher_id)
        publisher.trusted_signing_key_fingerprint = compute_fingerprint(public_key_pem)
        return await self._publishers.update(publisher)

    def is_trusted_signer(
        self, publisher: PluginPublisher, *, signer_key_fingerprint: str | None
    ) -> bool:
        """Whether *signer_key_fingerprint* matches this publisher's own
        registered trusted signing key.
        """
        return (
            publisher.trusted_signing_key_fingerprint is not None
            and signer_key_fingerprint == publisher.trusted_signing_key_fingerprint
        )


__all__ = ["PluginPublisherService"]
