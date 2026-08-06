"""IdempotencyService and WebhookIdempotencyKeyRepository: duplicate detection,
reservation, settlement, and the unscoped expiry sweep (docs/057 "IDEMPOTENCY").

Against real PostgreSQL, in a SAVEPOINT-isolated session per test.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.models.enums import IdempotencyStatus
from app.models.idempotency import WebhookIdempotencyKey
from app.services.idempotency import IdempotencyCheck, IdempotencyService
from tests.conftest import ago, soon

pytestmark = pytest.mark.asyncio


class TestCheck:
    async def test_no_key_at_all_is_not_a_duplicate(self, idempotency_service, organization_id):
        result = await idempotency_service.check(organization_id, "missing-key")
        assert result == IdempotencyCheck(is_duplicate=False, existing_response=None)

    async def test_a_still_pending_key_is_not_yet_a_duplicate(self, idempotency_service, organization_id):
        await idempotency_service.reserve(organization_id, "pending-key")
        result = await idempotency_service.check(organization_id, "pending-key")
        assert result.is_duplicate is False
        assert result.existing_response is None

    async def test_a_completed_key_is_a_duplicate_with_its_response_replayed(
        self, idempotency_service, organization_id
    ):
        await idempotency_service.reserve(organization_id, "done-key")
        await idempotency_service.settle(
            organization_id, "done-key", response_snapshot={"status": 201, "id": "abc"}
        )
        result = await idempotency_service.check(organization_id, "done-key")
        assert result.is_duplicate is True
        assert result.existing_response == {"status": 201, "id": "abc"}

    async def test_is_scoped_to_its_own_organization(self, idempotency_service, organization_id):
        await idempotency_service.reserve(organization_id, "org-scoped-key")
        await idempotency_service.settle(organization_id, "org-scoped-key", response_snapshot={"a": 1})
        other_org = uuid.uuid4()
        result = await idempotency_service.check(other_org, "org-scoped-key")
        assert result.is_duplicate is False
        assert result.existing_response is None


class TestReserve:
    async def test_reserves_a_pending_key_with_its_own_future_expiry(
        self, idempotency_service, organization_id
    ):
        reserved = await idempotency_service.reserve(organization_id, "reserve-key")
        assert reserved.status == IdempotencyStatus.PENDING
        assert reserved.idempotency_key == "reserve-key"
        assert reserved.organization_id == organization_id
        assert reserved.expires_at > datetime.now(UTC)


class TestSettle:
    async def test_settles_a_reserved_key_to_completed(self, idempotency_service, organization_id):
        await idempotency_service.reserve(organization_id, "settle-key")
        settled = await idempotency_service.settle(
            organization_id, "settle-key", response_snapshot={"ok": True}
        )
        assert settled is not None
        assert settled.status == IdempotencyStatus.COMPLETED
        assert settled.response_snapshot == {"ok": True}

    async def test_settling_a_key_that_was_never_reserved_returns_none(
        self, idempotency_service, organization_id
    ):
        result = await idempotency_service.settle(
            organization_id, "never-reserved", response_snapshot={"ok": True}
        )
        assert result is None


class TestExpireDue:
    async def test_returns_zero_when_nothing_is_due(self, idempotency_service, organization_id):
        await idempotency_service.reserve(organization_id, "fresh-key")
        count = await idempotency_service.expire_due(now=datetime.now(UTC))
        assert count == 0

    async def test_expires_due_keys_across_multiple_organizations_in_one_call(
        self, idempotency_service, idempotency_repo, organization_id
    ):
        other_org = uuid.uuid4()
        await idempotency_repo.create(
            WebhookIdempotencyKey(
                organization_id=organization_id,
                idempotency_key="expired-1",
                status=IdempotencyStatus.PENDING,
                expires_at=ago(60),
            )
        )
        await idempotency_repo.create(
            WebhookIdempotencyKey(
                organization_id=other_org,
                idempotency_key="expired-2",
                status=IdempotencyStatus.COMPLETED,
                response_snapshot={"a": 1},
                expires_at=ago(1),
            )
        )
        await idempotency_repo.create(
            WebhookIdempotencyKey(
                organization_id=organization_id,
                idempotency_key="not-due-yet",
                status=IdempotencyStatus.PENDING,
                expires_at=soon(3600),
            )
        )

        count = await idempotency_service.expire_due(now=datetime.now(UTC))
        assert count == 2

        refreshed_first = await idempotency_repo.get_by_key(organization_id, "expired-1")
        refreshed_second = await idempotency_repo.get_by_key(other_org, "expired-2")
        refreshed_untouched = await idempotency_repo.get_by_key(organization_id, "not-due-yet")
        assert refreshed_first.status == IdempotencyStatus.EXPIRED
        assert refreshed_second.status == IdempotencyStatus.EXPIRED
        assert refreshed_untouched.status == IdempotencyStatus.PENDING

    async def test_respects_the_limit_parameter(self, idempotency_service, idempotency_repo, organization_id):
        for i in range(3):
            await idempotency_repo.create(
                WebhookIdempotencyKey(
                    organization_id=organization_id,
                    idempotency_key=f"limited-{i}",
                    status=IdempotencyStatus.PENDING,
                    expires_at=ago(60),
                )
            )
        count = await idempotency_service.expire_due(now=datetime.now(UTC), limit=2)
        assert count == 2


class TestRepository:
    """Direct repository coverage for the unscoped sweep query."""

    async def test_get_by_key_returns_none_when_absent(self, idempotency_repo, organization_id):
        assert await idempotency_repo.get_by_key(organization_id, "nope") is None

    async def test_get_by_key_is_scoped_to_its_own_organization(self, idempotency_repo, organization_id):
        await idempotency_repo.create(
            WebhookIdempotencyKey(
                organization_id=organization_id,
                idempotency_key="scoped-key",
                status=IdempotencyStatus.PENDING,
                expires_at=soon(3600),
            )
        )
        other_org = uuid.uuid4()
        assert await idempotency_repo.get_by_key(other_org, "scoped-key") is None

    async def test_list_expired_is_unscoped_across_organizations(self, idempotency_repo, organization_id):
        other_org = uuid.uuid4()
        await idempotency_repo.create(
            WebhookIdempotencyKey(
                organization_id=organization_id,
                idempotency_key="repo-expired-1",
                status=IdempotencyStatus.PENDING,
                expires_at=ago(60),
            )
        )
        await idempotency_repo.create(
            WebhookIdempotencyKey(
                organization_id=other_org,
                idempotency_key="repo-expired-2",
                status=IdempotencyStatus.PENDING,
                expires_at=ago(60),
            )
        )
        found = await idempotency_repo.list_expired(now=datetime.now(UTC))
        found_keys = {row.idempotency_key for row in found}
        assert "repo-expired-1" in found_keys
        assert "repo-expired-2" in found_keys

    async def test_list_expired_excludes_keys_not_yet_due(self, idempotency_repo, organization_id):
        await idempotency_repo.create(
            WebhookIdempotencyKey(
                organization_id=organization_id,
                idempotency_key="not-due-repo",
                status=IdempotencyStatus.PENDING,
                expires_at=soon(3600),
            )
        )
        found = await idempotency_repo.list_expired(now=datetime.now(UTC))
        found_keys = {row.idempotency_key for row in found}
        assert "not-due-repo" not in found_keys
