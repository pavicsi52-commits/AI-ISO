"""SignatureService and WebhookSignatureRepository: creation, rotation, decrypted lookup.

Against real PostgreSQL, in a SAVEPOINT-isolated session per test.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from shared_core.exceptions.not_found import NotFoundError

from app.models.enums import SecretStatus, SignatureAlgorithm
from app.repositories.signature import WebhookSignatureRepository
from app.services.signature import SignatureService


class TestCreate:
    async def test_creates_the_first_secret_as_active_version_one(
        self, signature_service: SignatureService, organization_id: uuid.UUID, make_endpoint
    ) -> None:
        endpoint = await make_endpoint()
        created = await signature_service.create(
            organization_id, endpoint_id=endpoint.id, secret="super-secret-value"
        )
        assert created.secret_version == 1
        assert created.status == SecretStatus.ACTIVE
        assert created.algorithm == SignatureAlgorithm.HMAC_SHA256
        assert created.organization_id == organization_id
        assert created.endpoint_id == endpoint.id

    async def test_creates_with_a_custom_algorithm(
        self, signature_service: SignatureService, organization_id: uuid.UUID, make_endpoint
    ) -> None:
        endpoint = await make_endpoint()
        created = await signature_service.create(
            organization_id,
            endpoint_id=endpoint.id,
            secret="super-secret-value",
            algorithm=SignatureAlgorithm.HMAC_SHA512,
        )
        assert created.algorithm == SignatureAlgorithm.HMAC_SHA512

    async def test_the_stored_ciphertext_is_not_the_plaintext_secret(
        self,
        signature_service: SignatureService,
        signatures_repo: WebhookSignatureRepository,
        organization_id: uuid.UUID,
        make_endpoint,
    ) -> None:
        endpoint = await make_endpoint()
        created = await signature_service.create(
            organization_id, endpoint_id=endpoint.id, secret="super-secret-value"
        )
        raw = await signatures_repo.get_by_id(created.id)
        assert raw is not None
        assert raw.secret_ciphertext != "super-secret-value"
        assert "super-secret-value" not in raw.secret_ciphertext

    async def test_a_second_create_call_increments_the_version(
        self, signature_service: SignatureService, organization_id: uuid.UUID, make_endpoint
    ) -> None:
        endpoint = await make_endpoint()
        await signature_service.create(
            organization_id, endpoint_id=endpoint.id, secret="first-secret12"
        )
        second = await signature_service.create(
            organization_id, endpoint_id=endpoint.id, secret="second-secret12"
        )
        assert second.secret_version == 2


class TestRotate:
    async def test_rotating_with_no_prior_secret_creates_version_one_active(
        self, signature_service: SignatureService, organization_id: uuid.UUID, make_endpoint
    ) -> None:
        endpoint = await make_endpoint()
        rotated = await signature_service.rotate(
            organization_id, endpoint_id=endpoint.id, new_secret="brand-new-secret"
        )
        assert rotated.secret_version == 1
        assert rotated.status == SecretStatus.ACTIVE
        assert rotated.algorithm == SignatureAlgorithm.HMAC_SHA256

    async def test_rotating_moves_the_previous_active_secret_to_rotating(
        self,
        signature_service: SignatureService,
        signatures_repo: WebhookSignatureRepository,
        organization_id: uuid.UUID,
        make_endpoint,
        make_signature,
    ) -> None:
        endpoint = await make_endpoint()
        original = await make_signature(endpoint.id, secret="original-secret1")
        rotated = await signature_service.rotate(
            organization_id,
            endpoint_id=endpoint.id,
            new_secret="rotated-secret12",
            overlap_hours=24,
        )
        assert rotated.secret_version == original.secret_version + 1
        assert rotated.status == SecretStatus.ACTIVE

        raw_original = await signatures_repo.get_by_id(original.id)
        assert raw_original is not None
        assert raw_original.status == SecretStatus.ROTATING
        assert raw_original.rotated_at is not None
        assert raw_original.expires_at is not None
        assert raw_original.expires_at > datetime.now(UTC) + timedelta(hours=23)

    async def test_repeated_rotation_assigns_strictly_sequential_versions(
        self,
        signature_service: SignatureService,
        signatures_repo: WebhookSignatureRepository,
        organization_id: uuid.UUID,
        make_endpoint,
        make_signature,
    ) -> None:
        """Regression test.

        ``WebhookSignature`` used to define its own ``version`` column,
        shadowing ``BaseModel``'s generic optimistic-locking ``version``
        column of the same name. Every plain ``.update()`` call (e.g.
        demoting the previous secret to ``ROTATING``) silently
        incremented that shared counter as an unrelated side effect,
        which inflated/skewed the rotation ordinal on every rotation and
        eventually collided with a version number already used by
        another row of the same endpoint, failing the
        ``(endpoint_id, secret_version)`` uniqueness constraint. Renaming
        the domain field to ``secret_version`` (see ``app/models
        /signature.py``) fixed it -- this asserts every rotation still
        gets back-to-back sequential numbers, with no gaps and no
        collisions, across several rotations and an expiry sweep in
        between.
        """
        endpoint = await make_endpoint()
        first = await make_signature(endpoint.id, secret="secret-number-one")
        assert first.secret_version == 1

        second = await signature_service.rotate(
            organization_id,
            endpoint_id=endpoint.id,
            new_secret="secret-number-two",
            overlap_hours=0,
        )
        assert second.secret_version == 2

        # Expire the now-due ROTATING secret in between rotations -- this
        # is exactly the sequence that used to raise DuplicateRecordError.
        await signature_service.expire_due(now=datetime.now(UTC) + timedelta(seconds=1))

        third = await signature_service.rotate(
            organization_id,
            endpoint_id=endpoint.id,
            new_secret="secret-number-three",
            overlap_hours=0,
        )
        assert third.secret_version == 3

    async def test_the_rotated_secret_keeps_the_previous_algorithm(
        self,
        signature_service: SignatureService,
        organization_id: uuid.UUID,
        make_endpoint,
        make_signature,
    ) -> None:
        endpoint = await make_endpoint()
        await make_signature(
            endpoint.id, secret="original-secret1", algorithm=SignatureAlgorithm.HMAC_SHA512
        )
        rotated = await signature_service.rotate(
            organization_id, endpoint_id=endpoint.id, new_secret="rotated-secret12"
        )
        assert rotated.algorithm == SignatureAlgorithm.HMAC_SHA512

    async def test_the_old_secret_still_verifies_via_usable_secrets_immediately_after_rotation(
        self,
        signature_service: SignatureService,
        organization_id: uuid.UUID,
        make_endpoint,
        make_signature,
    ) -> None:
        endpoint = await make_endpoint()
        await make_signature(endpoint.id, secret="original-secret1")
        await signature_service.rotate(
            organization_id,
            endpoint_id=endpoint.id,
            new_secret="rotated-secret12",
            overlap_hours=24,
        )

        usable = await signature_service.usable_secrets_for(endpoint.id)
        secrets = {one.secret for one in usable}
        assert "original-secret1" in secrets
        assert "rotated-secret12" in secrets

    async def test_active_secret_for_returns_only_the_new_secret_after_rotation(
        self,
        signature_service: SignatureService,
        organization_id: uuid.UUID,
        make_endpoint,
        make_signature,
    ) -> None:
        endpoint = await make_endpoint()
        await make_signature(endpoint.id, secret="original-secret1")
        await signature_service.rotate(
            organization_id,
            endpoint_id=endpoint.id,
            new_secret="rotated-secret12",
            overlap_hours=24,
        )

        active = await signature_service.active_secret_for(endpoint.id)
        assert active is not None
        assert active.secret == "rotated-secret12"


class TestUsableSecretsFor:
    async def test_returns_empty_when_no_secret_exists(
        self, signature_service: SignatureService, make_endpoint
    ) -> None:
        endpoint = await make_endpoint()
        assert await signature_service.usable_secrets_for(endpoint.id) == []

    async def test_decrypts_the_stored_secret(
        self, signature_service: SignatureService, make_endpoint, make_signature
    ) -> None:
        endpoint = await make_endpoint()
        await make_signature(endpoint.id, secret="round-trip-me-1")
        [usable] = await signature_service.usable_secrets_for(endpoint.id)
        assert usable.secret == "round-trip-me-1"
        assert usable.algorithm == SignatureAlgorithm.HMAC_SHA256
        assert usable.version == 1

    async def test_orders_newest_version_first(
        self,
        signature_service: SignatureService,
        organization_id: uuid.UUID,
        make_endpoint,
        make_signature,
    ) -> None:
        endpoint = await make_endpoint()
        await make_signature(endpoint.id, secret="original-secret1")
        await signature_service.rotate(
            organization_id, endpoint_id=endpoint.id, new_secret="rotated-secret12"
        )
        usable = await signature_service.usable_secrets_for(endpoint.id)
        versions = [one.version for one in usable]
        assert versions == sorted(versions, reverse=True)


class TestActiveSecretFor:
    async def test_returns_none_when_no_secret_exists(
        self, signature_service: SignatureService, make_endpoint
    ) -> None:
        endpoint = await make_endpoint()
        assert await signature_service.active_secret_for(endpoint.id) is None

    async def test_returns_the_decrypted_active_secret(
        self, signature_service: SignatureService, make_endpoint, make_signature
    ) -> None:
        endpoint = await make_endpoint()
        await make_signature(endpoint.id, secret="active-secret-1")
        active = await signature_service.active_secret_for(endpoint.id)
        assert active is not None
        assert active.secret == "active-secret-1"


class TestExpireDue:
    async def test_expires_a_rotating_secret_past_its_overlap(
        self,
        signature_service: SignatureService,
        signatures_repo: WebhookSignatureRepository,
        organization_id: uuid.UUID,
        make_endpoint,
        make_signature,
    ) -> None:
        endpoint = await make_endpoint()
        original = await make_signature(endpoint.id, secret="original-secret1")
        await signature_service.rotate(
            organization_id, endpoint_id=endpoint.id, new_secret="rotated-secret12", overlap_hours=0
        )

        expired_count = await signature_service.expire_due(
            now=datetime.now(UTC) + timedelta(seconds=1)
        )
        assert expired_count == 1

        raw_original = await signatures_repo.get_by_id(original.id)
        assert raw_original is not None
        assert raw_original.status == SecretStatus.EXPIRED

    async def test_does_not_expire_a_rotating_secret_still_within_its_overlap(
        self,
        signature_service: SignatureService,
        signatures_repo: WebhookSignatureRepository,
        organization_id: uuid.UUID,
        make_endpoint,
        make_signature,
    ) -> None:
        endpoint = await make_endpoint()
        original = await make_signature(endpoint.id, secret="original-secret1")
        await signature_service.rotate(
            organization_id,
            endpoint_id=endpoint.id,
            new_secret="rotated-secret12",
            overlap_hours=24,
        )

        expired_count = await signature_service.expire_due(now=datetime.now(UTC))
        assert expired_count == 0

        raw_original = await signatures_repo.get_by_id(original.id)
        assert raw_original is not None
        assert raw_original.status == SecretStatus.ROTATING

    async def test_does_not_touch_an_active_secret(
        self,
        signature_service: SignatureService,
        signatures_repo: WebhookSignatureRepository,
        make_endpoint,
        make_signature,
    ) -> None:
        endpoint = await make_endpoint()
        active = await make_signature(endpoint.id, secret="active-secret-1")
        await signature_service.expire_due(now=datetime.now(UTC) + timedelta(days=365))
        raw_active = await signatures_repo.get_by_id(active.id)
        assert raw_active is not None
        assert raw_active.status == SecretStatus.ACTIVE

    async def test_respects_the_limit(
        self,
        signature_service: SignatureService,
        organization_id: uuid.UUID,
        make_endpoint,
        make_signature,
    ) -> None:
        endpoint_a = await make_endpoint(name="endpoint-a")
        endpoint_b = await make_endpoint(name="endpoint-b")
        await make_signature(endpoint_a.id, secret="secret-a-value1")
        await make_signature(endpoint_b.id, secret="secret-b-value1")
        await signature_service.rotate(
            organization_id,
            endpoint_id=endpoint_a.id,
            new_secret="secret-a-value2",
            overlap_hours=0,
        )
        await signature_service.rotate(
            organization_id,
            endpoint_id=endpoint_b.id,
            new_secret="secret-b-value2",
            overlap_hours=0,
        )

        expired_count = await signature_service.expire_due(
            now=datetime.now(UTC) + timedelta(seconds=1), limit=1
        )
        assert expired_count == 1


class TestWebhookSignatureRepository:
    """Direct repository-level coverage for paths no service method reaches."""

    async def test_require_in_org_returns_the_matching_row(
        self,
        signatures_repo: WebhookSignatureRepository,
        organization_id: uuid.UUID,
        make_endpoint,
        make_signature,
    ) -> None:
        endpoint = await make_endpoint()
        created = await make_signature(endpoint.id)
        found = await signatures_repo.require_in_org(organization_id, created.id)
        assert found.id == created.id

    async def test_require_in_org_raises_not_found_for_other_org(
        self, signatures_repo: WebhookSignatureRepository, make_endpoint, make_signature
    ) -> None:
        endpoint = await make_endpoint()
        created = await make_signature(endpoint.id)
        with pytest.raises(NotFoundError):
            await signatures_repo.require_in_org(uuid.uuid4(), created.id)

    async def test_get_latest_version_is_zero_when_no_secret_exists(
        self, signatures_repo: WebhookSignatureRepository, make_endpoint
    ) -> None:
        endpoint = await make_endpoint()
        assert await signatures_repo.get_latest_version(endpoint.id) == 0

    async def test_get_active_for_endpoint_returns_none_when_no_secret_exists(
        self, signatures_repo: WebhookSignatureRepository, make_endpoint
    ) -> None:
        endpoint = await make_endpoint()
        assert await signatures_repo.get_active_for_endpoint(endpoint.id) is None

    async def test_list_rotating_due_for_expiry_is_unscoped_by_organization(
        self,
        signatures_repo: WebhookSignatureRepository,
        signature_service: SignatureService,
        organization_id: uuid.UUID,
        make_endpoint,
        make_signature,
    ) -> None:
        endpoint = await make_endpoint()
        await make_signature(endpoint.id, secret="original-secret1")
        await signature_service.rotate(
            organization_id, endpoint_id=endpoint.id, new_secret="rotated-secret12", overlap_hours=0
        )
        due = await signatures_repo.list_rotating_due_for_expiry(
            now=datetime.now(UTC) + timedelta(seconds=1)
        )
        assert len(due) == 1
