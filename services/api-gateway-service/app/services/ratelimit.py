"""Rate limit policy management and enforcement."""

from __future__ import annotations

from uuid import UUID

from shared_core.cache.manager import CacheManager

from app.models.enums import RateLimitAlgorithm, RateLimitScope
from app.models.ratelimit import ApiRateLimitPolicy
from app.ratelimiting import engine as ratelimiting_engine
from app.ratelimiting.engine import RateLimitDecision
from app.repositories.ratelimit import ApiRateLimitPolicyRepository


class RateLimitService:
    """Rate-limit policies: configuration and enforcement."""

    def __init__(self, policies: ApiRateLimitPolicyRepository, cache_manager: CacheManager) -> None:
        self._policies = policies
        self._cache_manager = cache_manager

    async def set_policy(
        self,
        organization_id: UUID,
        *,
        scope: RateLimitScope,
        scope_reference: str | None,
        max_requests: int,
        window_seconds: int,
        algorithm: RateLimitAlgorithm = RateLimitAlgorithm.SLIDING_WINDOW,
        burst_max_requests: int | None = None,
        burst_window_seconds: int | None = None,
    ) -> ApiRateLimitPolicy:
        """Create or replace the policy for this exact scope/reference."""
        existing = await self._policies.find(organization_id, scope, scope_reference)
        if existing is None:
            return await self._policies.create(
                ApiRateLimitPolicy(
                    organization_id=organization_id,
                    scope=scope,
                    scope_reference=scope_reference,
                    algorithm=algorithm,
                    max_requests=max_requests,
                    window_seconds=window_seconds,
                    burst_max_requests=burst_max_requests,
                    burst_window_seconds=burst_window_seconds,
                )
            )
        existing.algorithm = algorithm
        existing.max_requests = max_requests
        existing.window_seconds = window_seconds
        existing.burst_max_requests = burst_max_requests
        existing.burst_window_seconds = burst_window_seconds
        return await self._policies.update(existing)

    async def list_policies(self, organization_id: UUID) -> list[ApiRateLimitPolicy]:
        """Every rate-limit policy configured in this organization."""
        return await self._policies.list_for_org(organization_id)

    async def check(
        self, organization_id: UUID, scope: RateLimitScope, scope_reference: str | None
    ) -> RateLimitDecision:
        """Check whether a call in this scope is currently allowed.

        A scope with no configured policy is unlimited (``allowed=True``,
        ``remaining=-1``) -- rate limiting is opt-in per scope, not a
        default every organization must configure before its first
        request succeeds.
        """
        policy = await self._policies.find(organization_id, scope, scope_reference)
        if policy is None or not policy.enabled:
            return RateLimitDecision(allowed=True, remaining=-1)
        limiter = ratelimiting_engine.build_rate_limiter(
            self._cache_manager,
            algorithm=policy.algorithm,
            max_requests=policy.max_requests,
            window_seconds=policy.window_seconds,
        )
        identifier = ratelimiting_engine.build_identifier(scope, scope_reference)
        return await ratelimiting_engine.check_rate_limit(
            limiter, f"gateway:{organization_id}:{identifier}"
        )


__all__ = ["RateLimitService"]
