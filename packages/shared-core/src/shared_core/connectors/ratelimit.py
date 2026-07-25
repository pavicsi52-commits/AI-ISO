"""Rate limiting.

Per docs/027_Enterprise_Connector_SDK.md.txt "RATE LIMITING": Per
Connector, Per Target, Per Organization, Per Project, Burst Control.
Reuses :class:`shared_core.cache.ratelimit.RateLimitCache` (Prompt 019,
already a distributed-safe fixed-window counter with penalty/block
support) rather than a second rate limiter. Every scope's identifier is
prefixed (``connector:``/``target:``/``org:``/``project:``) before
checking -- otherwise a connector name and an organization ID with the
same literal string value would silently share one counter, the exact
bug :mod:`shared_core.notifications.ratelimit` hit and fixed in Prompt
025.
"""

from __future__ import annotations

from dataclasses import dataclass

from shared_core.cache.manager import CacheManager
from shared_core.cache.ratelimit import RateLimitCache, RateLimitStatus
from shared_core.connectors.constants import DEFAULT_RATE_LIMIT_BURST, DEFAULT_RATE_LIMIT_PER_SECOND


@dataclass(frozen=True, slots=True)
class ConnectorRateLimiter:
    """Scope-isolated rate limiting for connector operations ("Burst Control")."""

    per_connector: RateLimitCache
    per_target: RateLimitCache
    per_organization: RateLimitCache
    per_project: RateLimitCache

    async def check_connector(self, provider_name: str) -> RateLimitStatus:
        """Check the per-connector-provider scope ("Per Connector")."""
        return await self.per_connector.check(f"connector:{provider_name}")

    async def check_target(self, host: str) -> RateLimitStatus:
        """Check the per-target scope ("Per Target")."""
        return await self.per_target.check(f"target:{host}")

    async def check_organization(self, organization_id: str) -> RateLimitStatus:
        """Check the per-organization scope ("Per Organization")."""
        return await self.per_organization.check(f"org:{organization_id}")

    async def check_project(self, project_id: str) -> RateLimitStatus:
        """Check the per-project scope ("Per Project")."""
        return await self.per_project.check(f"project:{project_id}")


def build_connector_rate_limiters(
    cache: CacheManager,
    *,
    max_requests: int = DEFAULT_RATE_LIMIT_PER_SECOND,
    burst: int = DEFAULT_RATE_LIMIT_BURST,
    window_seconds: int = 1,
) -> ConnectorRateLimiter:
    """Build a :class:`ConnectorRateLimiter` with one independent cache per scope."""
    limit = max_requests + burst
    return ConnectorRateLimiter(
        per_connector=RateLimitCache(cache, max_requests=limit, window_seconds=window_seconds),
        per_target=RateLimitCache(cache, max_requests=limit, window_seconds=window_seconds),
        per_organization=RateLimitCache(cache, max_requests=limit, window_seconds=window_seconds),
        per_project=RateLimitCache(cache, max_requests=limit, window_seconds=window_seconds),
    )


__all__ = ["ConnectorRateLimiter", "build_connector_rate_limiters"]
