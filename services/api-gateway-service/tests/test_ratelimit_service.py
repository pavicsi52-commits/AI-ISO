"""RateLimitService and ApiRateLimitPolicyRepository: policy configuration and enforcement.

Against real PostgreSQL and real Redis, in a SAVEPOINT-isolated session per
test. No mocking -- ``RateLimitService.check`` drives the real
``shared_core`` limiter primitives (``RateLimitCache`` /
``DistributedRateLimiter``) against the test's own Redis db 29.
"""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError

from app.models.enums import RateLimitAlgorithm, RateLimitScope
from app.models.ratelimit import ApiRateLimitPolicy
from app.repositories.ratelimit import ApiRateLimitPolicyRepository
from app.services.ratelimit import RateLimitService

pytestmark = pytest.mark.asyncio


class TestSetPolicy:
    async def test_creates_a_new_policy(
        self, rate_limit_service: RateLimitService, organization_id: uuid.UUID
    ) -> None:
        policy = await rate_limit_service.set_policy(
            organization_id,
            scope=RateLimitScope.ORGANIZATION,
            scope_reference=None,
            max_requests=10,
            window_seconds=60,
        )
        assert policy.id is not None
        assert policy.scope == RateLimitScope.ORGANIZATION
        assert policy.max_requests == 10
        assert policy.window_seconds == 60
        assert policy.algorithm == RateLimitAlgorithm.SLIDING_WINDOW
        assert policy.enabled is True
        assert policy.burst_max_requests is None
        assert policy.burst_window_seconds is None

    async def test_updates_the_existing_policy_for_the_same_scope_and_reference(
        self, rate_limit_service: RateLimitService, organization_id: uuid.UUID
    ) -> None:
        first = await rate_limit_service.set_policy(
            organization_id,
            scope=RateLimitScope.ENDPOINT,
            scope_reference="/orders",
            max_requests=5,
            window_seconds=60,
        )
        second = await rate_limit_service.set_policy(
            organization_id,
            scope=RateLimitScope.ENDPOINT,
            scope_reference="/orders",
            max_requests=25,
            window_seconds=120,
            algorithm=RateLimitAlgorithm.FIXED_WINDOW,
            burst_max_requests=5,
            burst_window_seconds=1,
        )
        assert second.id == first.id
        assert second.max_requests == 25
        assert second.window_seconds == 120
        assert second.algorithm == RateLimitAlgorithm.FIXED_WINDOW
        assert second.burst_max_requests == 5
        assert second.burst_window_seconds == 1

        all_policies = await rate_limit_service.list_policies(organization_id)
        assert len(all_policies) == 1


class TestListPolicies:
    async def test_scoped_to_the_organization(
        self, rate_limit_service: RateLimitService, organization_id: uuid.UUID
    ) -> None:
        await rate_limit_service.set_policy(
            organization_id,
            scope=RateLimitScope.GLOBAL,
            scope_reference=None,
            max_requests=1,
            window_seconds=60,
        )
        await rate_limit_service.set_policy(
            organization_id,
            scope=RateLimitScope.USER,
            scope_reference="user-1",
            max_requests=2,
            window_seconds=60,
        )
        other_org = uuid.uuid4()
        await rate_limit_service.set_policy(
            other_org,
            scope=RateLimitScope.GLOBAL,
            scope_reference=None,
            max_requests=99,
            window_seconds=60,
        )

        policies = await rate_limit_service.list_policies(organization_id)
        assert {p.scope for p in policies} == {RateLimitScope.GLOBAL, RateLimitScope.USER}
        assert all(p.organization_id == organization_id for p in policies)


class TestCheckUnconfiguredOrDisabled:
    async def test_a_scope_with_no_configured_policy_is_unlimited(
        self, rate_limit_service: RateLimitService, organization_id: uuid.UUID
    ) -> None:
        decision = await rate_limit_service.check(organization_id, RateLimitScope.USER, "nobody")
        assert decision.allowed is True
        assert decision.remaining == -1
        assert decision.retry_after_seconds is None

    async def test_a_disabled_policy_is_also_unlimited(
        self,
        rate_limits_repo: ApiRateLimitPolicyRepository,
        rate_limit_service: RateLimitService,
        organization_id: uuid.UUID,
    ) -> None:
        # RateLimitService.set_policy has no `enabled` parameter -- disabling
        # a policy is only reachable by writing the row directly, exactly
        # as an admin-toggle endpoint elsewhere in this service would.
        await rate_limits_repo.create(
            ApiRateLimitPolicy(
                organization_id=organization_id,
                scope=RateLimitScope.PROJECT,
                scope_reference="proj-1",
                algorithm=RateLimitAlgorithm.SLIDING_WINDOW,
                max_requests=1,
                window_seconds=60,
                enabled=False,
            )
        )
        decision = await rate_limit_service.check(organization_id, RateLimitScope.PROJECT, "proj-1")
        assert decision.allowed is True
        assert decision.remaining == -1


class TestCheckSlidingWindow:
    async def test_allows_until_the_limit_then_denies(
        self, rate_limit_service: RateLimitService, organization_id: uuid.UUID
    ) -> None:
        await rate_limit_service.set_policy(
            organization_id,
            scope=RateLimitScope.ENDPOINT,
            scope_reference="/sliding",
            max_requests=1,
            window_seconds=60,
            algorithm=RateLimitAlgorithm.SLIDING_WINDOW,
        )
        first = await rate_limit_service.check(organization_id, RateLimitScope.ENDPOINT, "/sliding")
        assert first.allowed is True
        assert first.remaining == 0
        assert first.retry_after_seconds is None

        second = await rate_limit_service.check(
            organization_id, RateLimitScope.ENDPOINT, "/sliding"
        )
        assert second.allowed is False
        assert second.remaining == 0
        assert second.retry_after_seconds is None


class TestCheckFixedWindowAndTokenBucket:
    async def test_fixed_window_denies_with_a_retry_after(
        self, rate_limit_service: RateLimitService, organization_id: uuid.UUID
    ) -> None:
        await rate_limit_service.set_policy(
            organization_id,
            scope=RateLimitScope.ENDPOINT,
            scope_reference="/fixed",
            max_requests=1,
            window_seconds=60,
            algorithm=RateLimitAlgorithm.FIXED_WINDOW,
        )
        first = await rate_limit_service.check(organization_id, RateLimitScope.ENDPOINT, "/fixed")
        assert first.allowed is True

        second = await rate_limit_service.check(organization_id, RateLimitScope.ENDPOINT, "/fixed")
        assert second.allowed is False
        assert second.remaining == 0
        assert second.retry_after_seconds is not None

    async def test_token_bucket_uses_the_same_counter_style_limiter(
        self, rate_limit_service: RateLimitService, organization_id: uuid.UUID
    ) -> None:
        await rate_limit_service.set_policy(
            organization_id,
            scope=RateLimitScope.API_KEY,
            scope_reference="key-1",
            max_requests=2,
            window_seconds=60,
            algorithm=RateLimitAlgorithm.TOKEN_BUCKET,
        )
        first = await rate_limit_service.check(organization_id, RateLimitScope.API_KEY, "key-1")
        second = await rate_limit_service.check(organization_id, RateLimitScope.API_KEY, "key-1")
        third = await rate_limit_service.check(organization_id, RateLimitScope.API_KEY, "key-1")
        assert first.allowed is True
        assert second.allowed is True
        assert third.allowed is False
        assert third.retry_after_seconds is not None


class TestCheckMultiTenantIsolation:
    async def test_two_organizations_at_the_same_scope_do_not_share_a_counter(
        self, rate_limit_service: RateLimitService, organization_id: uuid.UUID
    ) -> None:
        other_org = uuid.uuid4()
        await rate_limit_service.set_policy(
            organization_id,
            scope=RateLimitScope.GLOBAL,
            scope_reference=None,
            max_requests=1,
            window_seconds=60,
        )
        await rate_limit_service.set_policy(
            other_org,
            scope=RateLimitScope.GLOBAL,
            scope_reference=None,
            max_requests=1,
            window_seconds=60,
        )
        used = await rate_limit_service.check(organization_id, RateLimitScope.GLOBAL, None)
        assert used.allowed is True

        other_still_fresh = await rate_limit_service.check(other_org, RateLimitScope.GLOBAL, None)
        assert other_still_fresh.allowed is True


class TestRepositoryRequireInOrg:
    async def test_returns_the_policy_when_it_belongs_to_the_org(
        self,
        rate_limits_repo: ApiRateLimitPolicyRepository,
        rate_limit_service: RateLimitService,
        organization_id: uuid.UUID,
    ) -> None:
        created = await rate_limit_service.set_policy(
            organization_id,
            scope=RateLimitScope.GLOBAL,
            scope_reference=None,
            max_requests=1,
            window_seconds=60,
        )
        found = await rate_limits_repo.require_in_org(organization_id, created.id)
        assert found.id == created.id

    async def test_raises_not_found_for_an_unknown_id(
        self, rate_limits_repo: ApiRateLimitPolicyRepository, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await rate_limits_repo.require_in_org(organization_id, uuid.uuid4())

    async def test_raises_not_found_for_a_policy_owned_by_a_different_org(
        self,
        rate_limits_repo: ApiRateLimitPolicyRepository,
        rate_limit_service: RateLimitService,
        organization_id: uuid.UUID,
    ) -> None:
        created = await rate_limit_service.set_policy(
            organization_id,
            scope=RateLimitScope.GLOBAL,
            scope_reference=None,
            max_requests=1,
            window_seconds=60,
        )
        with pytest.raises(NotFoundError):
            await rate_limits_repo.require_in_org(uuid.uuid4(), created.id)


class TestRepositoryFind:
    async def test_returns_none_when_nothing_matches(
        self, rate_limits_repo: ApiRateLimitPolicyRepository, organization_id: uuid.UUID
    ) -> None:
        found = await rate_limits_repo.find(organization_id, RateLimitScope.USER, "ghost")
        assert found is None

    async def test_matches_on_exact_scope_and_reference_only(
        self,
        rate_limits_repo: ApiRateLimitPolicyRepository,
        rate_limit_service: RateLimitService,
        organization_id: uuid.UUID,
    ) -> None:
        await rate_limit_service.set_policy(
            organization_id,
            scope=RateLimitScope.USER,
            scope_reference="user-abc",
            max_requests=1,
            window_seconds=60,
        )
        assert (
            await rate_limits_repo.find(organization_id, RateLimitScope.USER, "user-abc")
            is not None
        )
        assert await rate_limits_repo.find(organization_id, RateLimitScope.USER, "user-xyz") is None
        assert await rate_limits_repo.find(organization_id, RateLimitScope.USER, None) is None
