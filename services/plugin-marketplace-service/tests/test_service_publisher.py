"""Tests for ``app.services.publisher.PluginPublisherService``."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.validation import ValidationError

from app.models.enums import PublisherType, PublisherVerificationStatus
from app.security.signer import compute_fingerprint, generate_signing_keypair
from app.services.publisher import PluginPublisherService


async def test_register_happy_path(
    publisher_service: PluginPublisherService, organization_id: uuid.UUID
) -> None:
    publisher = await publisher_service.register(
        organization_id,
        slug="acme-plugins",
        display_name="Acme Plugins Inc.",
        publisher_type=PublisherType.ORGANIZATION,
        contact_email="hello@acme.test",
        website_url="https://acme.test",
        bio="We make plugins.",
    )

    assert publisher.slug == "acme-plugins"
    assert publisher.display_name == "Acme Plugins Inc."
    assert publisher.publisher_type == PublisherType.ORGANIZATION
    assert publisher.contact_email == "hello@acme.test"
    assert publisher.website_url == "https://acme.test"
    assert publisher.bio == "We make plugins."
    assert publisher.verification_status == PublisherVerificationStatus.UNVERIFIED


async def test_register_duplicate_slug_in_same_org_raises(
    publisher_service: PluginPublisherService, organization_id: uuid.UUID
) -> None:
    await publisher_service.register(
        organization_id, slug="dup-slug", display_name="First"
    )

    with pytest.raises(ValidationError):
        await publisher_service.register(
            organization_id, slug="dup-slug", display_name="Second"
        )


async def test_register_same_slug_in_different_org_is_allowed(
    publisher_service: PluginPublisherService, organization_id: uuid.UUID
) -> None:
    other_org = uuid.uuid4()
    await publisher_service.register(organization_id, slug="shared-slug", display_name="Org A")
    other = await publisher_service.register(other_org, slug="shared-slug", display_name="Org B")

    assert other.slug == "shared-slug"


async def test_get_and_list_for_org(
    publisher_service: PluginPublisherService, organization_id: uuid.UUID
) -> None:
    first = await publisher_service.register(
        organization_id, slug="pub-a", display_name="Publisher A"
    )
    second = await publisher_service.register(
        organization_id, slug="pub-b", display_name="Publisher B"
    )

    fetched = await publisher_service.get(organization_id, first.id)
    assert fetched.id == first.id

    all_publishers = await publisher_service.list_for_org(organization_id)
    assert {p.id for p in all_publishers} == {first.id, second.id}


async def test_request_verification_sets_pending(
    publisher_service: PluginPublisherService, organization_id: uuid.UUID
) -> None:
    publisher = await publisher_service.register(
        organization_id, slug="pending-pub", display_name="Pending Publisher"
    )

    requested = await publisher_service.request_verification(organization_id, publisher.id)

    assert requested.verification_status == PublisherVerificationStatus.PENDING


async def test_verify_sets_verified_with_metadata(
    publisher_service: PluginPublisherService, organization_id: uuid.UUID
) -> None:
    publisher = await publisher_service.register(
        organization_id, slug="verify-pub", display_name="Verify Publisher"
    )
    await publisher_service.request_verification(organization_id, publisher.id)

    verified = await publisher_service.verify(
        organization_id, publisher.id, verified_by="admin-1"
    )

    assert verified.verification_status == PublisherVerificationStatus.VERIFIED
    assert verified.verified_at is not None
    assert verified.verified_by == "admin-1"


async def test_revoke_verification_sets_revoked(
    publisher_service: PluginPublisherService, organization_id: uuid.UUID
) -> None:
    publisher = await publisher_service.register(
        organization_id, slug="revoke-pub", display_name="Revoke Publisher"
    )
    await publisher_service.verify(organization_id, publisher.id, verified_by="admin-1")

    revoked = await publisher_service.revoke_verification(organization_id, publisher.id)

    assert revoked.verification_status == PublisherVerificationStatus.REVOKED


async def test_set_trusted_signing_key_matches_computed_fingerprint(
    publisher_service: PluginPublisherService, organization_id: uuid.UUID
) -> None:
    publisher = await publisher_service.register(
        organization_id, slug="signing-pub", display_name="Signing Publisher"
    )
    _private_pem, public_pem = generate_signing_keypair()

    updated = await publisher_service.set_trusted_signing_key(
        organization_id, publisher.id, public_key_pem=public_pem
    )

    assert updated.trusted_signing_key_fingerprint == compute_fingerprint(public_pem)


async def test_is_trusted_signer(
    publisher_service: PluginPublisherService, organization_id: uuid.UUID
) -> None:
    publisher = await publisher_service.register(
        organization_id, slug="trust-pub", display_name="Trust Publisher"
    )

    # No key set yet -- nothing is trusted.
    assert publisher_service.is_trusted_signer(publisher, signer_key_fingerprint="anything") is False
    assert publisher_service.is_trusted_signer(publisher, signer_key_fingerprint=None) is False

    _private_pem, public_pem = generate_signing_keypair()
    trusted_publisher = await publisher_service.set_trusted_signing_key(
        organization_id, publisher.id, public_key_pem=public_pem
    )
    fingerprint = compute_fingerprint(public_pem)

    assert (
        publisher_service.is_trusted_signer(trusted_publisher, signer_key_fingerprint=fingerprint)
        is True
    )

    _other_private_pem, other_public_pem = generate_signing_keypair()
    mismatched_fingerprint = compute_fingerprint(other_public_pem)
    assert (
        publisher_service.is_trusted_signer(
            trusted_publisher, signer_key_fingerprint=mismatched_fingerprint
        )
        is False
    )
