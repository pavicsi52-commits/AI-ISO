"""QuotaService and ApiQuotaPolicyRepository: quota configuration, usage tracking, and reset.

Against real PostgreSQL, in a SAVEPOINT-isolated session per test.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from shared_core.exceptions.not_found import NotFoundError

from app.models.enums import QuotaKind, QuotaPeriod, QuotaScope
from app.models.quota import ApiQuotaPolicy
from app.repositories.quota import ApiQuotaPolicyRepository
from app.services.quota import QuotaService

pytestmark = pytest.mark.asyncio


def _ago(seconds: int) -> datetime:
    return datetime.now(UTC) - timedelta(seconds=seconds)


def _soon(seconds: int) -> datetime:
    return datetime.now(UTC) + timedelta(seconds=seconds)


class TestSetPolicy:
    async def test_creates_a_new_quota_with_a_fresh_period(
        self, quota_service: QuotaService, organization_id: uuid.UUID
    ) -> None:
        before = datetime.now(UTC)
        policy = await quota_service.set_policy(
            organization_id,
            scope=QuotaScope.ORGANIZATION,
            scope_reference=None,
            kind=QuotaKind.REQUEST,
            period=QuotaPeriod.DAILY,
            limit_value=100,
        )
        assert policy.id is not None
        assert policy.limit_value == 100
        assert policy.used_value == 0.0
        assert policy.enabled is True
        assert policy.period_started_at <= before or policy.period_started_at <= datetime.now(UTC)
        assert policy.period_resets_at > before

    async def test_updates_period_and_limit_but_leaves_usage_and_window_alone(
        self, quota_service: QuotaService, organization_id: uuid.UUID
    ) -> None:
        first = await quota_service.set_policy(
            organization_id,
            scope=QuotaScope.PROJECT,
            scope_reference="proj-1",
            kind=QuotaKind.BANDWIDTH,
            period=QuotaPeriod.DAILY,
            limit_value=10,
        )
        second = await quota_service.set_policy(
            organization_id,
            scope=QuotaScope.PROJECT,
            scope_reference="proj-1",
            kind=QuotaKind.BANDWIDTH,
            period=QuotaPeriod.MONTHLY,
            limit_value=999,
        )
        assert second.id == first.id
        assert second.limit_value == 999
        assert second.period == QuotaPeriod.MONTHLY
        # set_policy's update branch does not touch usage or the window --
        # only check_and_increment/reset_due ever recompute those.
        assert second.used_value == first.used_value
        assert second.period_started_at == first.period_started_at
        assert second.period_resets_at == first.period_resets_at

        all_policies = await quota_service.list_policies(organization_id)
        assert len(all_policies) == 1


class TestListPolicies:
    async def test_scoped_to_the_organization(
        self, quota_service: QuotaService, organization_id: uuid.UUID
    ) -> None:
        await quota_service.set_policy(
            organization_id,
            scope=QuotaScope.GLOBAL,
            scope_reference=None,
            kind=QuotaKind.REQUEST,
            period=QuotaPeriod.DAILY,
            limit_value=1,
        )
        other_org = uuid.uuid4()
        await quota_service.set_policy(
            other_org,
            scope=QuotaScope.GLOBAL,
            scope_reference=None,
            kind=QuotaKind.REQUEST,
            period=QuotaPeriod.DAILY,
            limit_value=1,
        )
        policies = await quota_service.list_policies(organization_id)
        assert len(policies) == 1
        assert policies[0].organization_id == organization_id


class TestCheckAndIncrementUnconfiguredOrDisabled:
    async def test_a_scope_with_no_configured_quota_is_unlimited(
        self, quota_service: QuotaService, organization_id: uuid.UUID
    ) -> None:
        allowed = await quota_service.check_and_increment(
            organization_id, QuotaScope.CLIENT, "client-1", QuotaKind.REQUEST
        )
        assert allowed is True

    async def test_a_disabled_quota_is_also_unlimited_and_usage_is_untouched(
        self,
        quotas_repo: ApiQuotaPolicyRepository,
        quota_service: QuotaService,
        organization_id: uuid.UUID,
    ) -> None:
        now = datetime.now(UTC)
        await quotas_repo.create(
            ApiQuotaPolicy(
                organization_id=organization_id,
                scope=QuotaScope.CLIENT,
                scope_reference="client-disabled",
                kind=QuotaKind.REQUEST,
                period=QuotaPeriod.DAILY,
                limit_value=1,
                used_value=1.0,
                period_started_at=now,
                period_resets_at=_soon(3600),
                enabled=False,
            )
        )
        allowed = await quota_service.check_and_increment(
            organization_id, QuotaScope.CLIENT, "client-disabled", QuotaKind.REQUEST
        )
        assert allowed is True
        policy = await quotas_repo.find(
            organization_id, QuotaScope.CLIENT, "client-disabled", QuotaKind.REQUEST
        )
        assert policy is not None
        assert policy.used_value == 1.0


class TestCheckAndIncrementWithinLimit:
    async def test_increments_usage_and_allows_while_under_the_limit(
        self, quota_service: QuotaService, organization_id: uuid.UUID
    ) -> None:
        await quota_service.set_policy(
            organization_id,
            scope=QuotaScope.ORGANIZATION,
            scope_reference=None,
            kind=QuotaKind.REQUEST,
            period=QuotaPeriod.DAILY,
            limit_value=2,
        )
        first = await quota_service.check_and_increment(
            organization_id, QuotaScope.ORGANIZATION, None, QuotaKind.REQUEST
        )
        second = await quota_service.check_and_increment(
            organization_id, QuotaScope.ORGANIZATION, None, QuotaKind.REQUEST
        )
        assert first is True
        assert second is True

    async def test_custom_amount_increments_by_more_than_one(
        self,
        quota_service: QuotaService,
        quotas_repo: ApiQuotaPolicyRepository,
        organization_id: uuid.UUID,
    ) -> None:
        await quota_service.set_policy(
            organization_id,
            scope=QuotaScope.ORGANIZATION,
            scope_reference=None,
            kind=QuotaKind.STORAGE,
            period=QuotaPeriod.DAILY,
            limit_value=1000,
        )
        allowed = await quota_service.check_and_increment(
            organization_id, QuotaScope.ORGANIZATION, None, QuotaKind.STORAGE, amount=250.5
        )
        assert allowed is True
        policy = await quotas_repo.find(
            organization_id, QuotaScope.ORGANIZATION, None, QuotaKind.STORAGE
        )
        assert policy is not None
        assert policy.used_value == 250.5


class TestCheckAndIncrementExhausted:
    async def test_denies_once_the_limit_is_reached_and_leaves_usage_unchanged(
        self,
        quota_service: QuotaService,
        quotas_repo: ApiQuotaPolicyRepository,
        organization_id: uuid.UUID,
    ) -> None:
        await quota_service.set_policy(
            organization_id,
            scope=QuotaScope.ORGANIZATION,
            scope_reference=None,
            kind=QuotaKind.REQUEST,
            period=QuotaPeriod.DAILY,
            limit_value=1,
        )
        first = await quota_service.check_and_increment(
            organization_id, QuotaScope.ORGANIZATION, None, QuotaKind.REQUEST
        )
        second = await quota_service.check_and_increment(
            organization_id, QuotaScope.ORGANIZATION, None, QuotaKind.REQUEST
        )
        assert first is True
        assert second is False

        policy = await quotas_repo.find(
            organization_id, QuotaScope.ORGANIZATION, None, QuotaKind.REQUEST
        )
        assert policy is not None
        assert policy.used_value == 1.0


class TestCheckAndIncrementPeriodExpiry:
    async def test_a_request_after_period_resets_at_gets_a_clean_slate_not_a_stale_refusal(
        self,
        quota_service: QuotaService,
        quotas_repo: ApiQuotaPolicyRepository,
        organization_id: uuid.UUID,
    ) -> None:
        # A quota that is already fully exhausted, but whose tracked window
        # ended in the past -- the exact "stale window" scenario the sweep
        # exists to prevent a caller from being wrongly refused against.
        # An explicitly stale, long-past window (not just "a few hours
        # ago", which on a `DAILY` period could still land on the same
        # calendar day as `now` and make `period_started_at` coincide with
        # today's recomputed start) so the reset is unambiguous.
        long_ago = datetime(2020, 1, 1, tzinfo=UTC)
        stale = ApiQuotaPolicy(
            organization_id=organization_id,
            scope=QuotaScope.CLIENT,
            scope_reference="client-stale",
            kind=QuotaKind.REQUEST,
            period=QuotaPeriod.DAILY,
            limit_value=1,
            used_value=1.0,
            period_started_at=long_ago,
            period_resets_at=long_ago + timedelta(days=1),
        )
        await quotas_repo.create(stale)
        # `find` below returns this exact same identity-mapped ORM object
        # (one session, one identity map) -- `stale.period_started_at`
        # would read back already-mutated after `check_and_increment`, so
        # the original value is captured now, before that call.
        original_started_at = stale.period_started_at

        allowed = await quota_service.check_and_increment(
            organization_id, QuotaScope.CLIENT, "client-stale", QuotaKind.REQUEST
        )
        assert allowed is True

        refreshed = await quotas_repo.find(
            organization_id, QuotaScope.CLIENT, "client-stale", QuotaKind.REQUEST
        )
        assert refreshed is not None
        assert refreshed.used_value == 1.0  # reset to 0, then incremented by the default amount=1
        assert refreshed.period_resets_at > datetime.now(UTC)
        assert refreshed.period_started_at > original_started_at


class TestResetDue:
    async def test_returns_zero_when_nothing_is_due(self, quota_service: QuotaService) -> None:
        count = await quota_service.reset_due(now=datetime.now(UTC))
        assert count == 0

    async def test_resets_due_quotas_across_multiple_organizations_in_one_call(
        self,
        quota_service: QuotaService,
        quotas_repo: ApiQuotaPolicyRepository,
        organization_id: uuid.UUID,
    ) -> None:
        other_org = uuid.uuid4()
        now = datetime.now(UTC)

        due_here = ApiQuotaPolicy(
            organization_id=organization_id,
            scope=QuotaScope.ORGANIZATION,
            scope_reference=None,
            kind=QuotaKind.REQUEST,
            period=QuotaPeriod.DAILY,
            limit_value=5,
            used_value=5.0,
            period_started_at=_ago(7200),
            period_resets_at=_ago(1),
        )
        due_other_org = ApiQuotaPolicy(
            organization_id=other_org,
            scope=QuotaScope.ORGANIZATION,
            scope_reference=None,
            kind=QuotaKind.BANDWIDTH,
            period=QuotaPeriod.MONTHLY,
            limit_value=5,
            used_value=5.0,
            period_started_at=_ago(7200),
            period_resets_at=_ago(1),
        )
        not_due = ApiQuotaPolicy(
            organization_id=organization_id,
            scope=QuotaScope.CLIENT,
            scope_reference="still-fresh",
            kind=QuotaKind.REQUEST,
            period=QuotaPeriod.DAILY,
            limit_value=5,
            used_value=3.0,
            period_started_at=_ago(60),
            period_resets_at=_soon(3600),
        )
        await quotas_repo.create(due_here)
        await quotas_repo.create(due_other_org)
        await quotas_repo.create(not_due)

        count = await quota_service.reset_due(now=now)
        assert count == 2

        refreshed_here = await quotas_repo.find(
            organization_id, QuotaScope.ORGANIZATION, None, QuotaKind.REQUEST
        )
        refreshed_other = await quotas_repo.find(
            other_org, QuotaScope.ORGANIZATION, None, QuotaKind.BANDWIDTH
        )
        refreshed_not_due = await quotas_repo.find(
            organization_id, QuotaScope.CLIENT, "still-fresh", QuotaKind.REQUEST
        )

        assert refreshed_here is not None and refreshed_here.used_value == 0.0
        assert refreshed_other is not None and refreshed_other.used_value == 0.0
        assert refreshed_not_due is not None and refreshed_not_due.used_value == 3.0  # untouched

    async def test_respects_the_limit_parameter(
        self,
        quota_service: QuotaService,
        quotas_repo: ApiQuotaPolicyRepository,
        organization_id: uuid.UUID,
    ) -> None:
        for index in range(3):
            await quotas_repo.create(
                ApiQuotaPolicy(
                    organization_id=organization_id,
                    scope=QuotaScope.CLIENT,
                    scope_reference=f"client-{index}",
                    kind=QuotaKind.REQUEST,
                    period=QuotaPeriod.DAILY,
                    limit_value=5,
                    used_value=5.0,
                    period_started_at=_ago(7200),
                    period_resets_at=_ago(1),
                )
            )
        count = await quota_service.reset_due(now=datetime.now(UTC), limit=2)
        assert count == 2


class TestRepositoryRequireInOrg:
    async def test_returns_the_quota_when_it_belongs_to_the_org(
        self,
        quotas_repo: ApiQuotaPolicyRepository,
        quota_service: QuotaService,
        organization_id: uuid.UUID,
    ) -> None:
        created = await quota_service.set_policy(
            organization_id,
            scope=QuotaScope.GLOBAL,
            scope_reference=None,
            kind=QuotaKind.REQUEST,
            period=QuotaPeriod.DAILY,
            limit_value=1,
        )
        found = await quotas_repo.require_in_org(organization_id, created.id)
        assert found.id == created.id

    async def test_raises_not_found_for_an_unknown_id(
        self, quotas_repo: ApiQuotaPolicyRepository, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await quotas_repo.require_in_org(organization_id, uuid.uuid4())

    async def test_raises_not_found_for_a_quota_owned_by_a_different_org(
        self,
        quotas_repo: ApiQuotaPolicyRepository,
        quota_service: QuotaService,
        organization_id: uuid.UUID,
    ) -> None:
        created = await quota_service.set_policy(
            organization_id,
            scope=QuotaScope.GLOBAL,
            scope_reference=None,
            kind=QuotaKind.REQUEST,
            period=QuotaPeriod.DAILY,
            limit_value=1,
        )
        with pytest.raises(NotFoundError):
            await quotas_repo.require_in_org(uuid.uuid4(), created.id)


class TestRepositoryFind:
    async def test_returns_none_when_kind_does_not_match(
        self,
        quotas_repo: ApiQuotaPolicyRepository,
        quota_service: QuotaService,
        organization_id: uuid.UUID,
    ) -> None:
        await quota_service.set_policy(
            organization_id,
            scope=QuotaScope.PROJECT,
            scope_reference="proj-x",
            kind=QuotaKind.REQUEST,
            period=QuotaPeriod.DAILY,
            limit_value=1,
        )
        found = await quotas_repo.find(
            organization_id, QuotaScope.PROJECT, "proj-x", QuotaKind.BANDWIDTH
        )
        assert found is None
