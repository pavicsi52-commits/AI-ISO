"""Notification rate limiting.

Per docs/025_Enterprise_Notification_Framework.md.txt "RATE LIMITING":
Per User, Per Organization, Per Channel, Per Provider, Global Limits.
Reuses :class:`shared_core.cache.ratelimit.RateLimitCache` directly
(fixed-window counting with an escalating penalty block, already
distributed-safe via Redis) rather than reimplementing rate limiting a
second time -- this module only builds the per-scope identifiers.
("Per Provider" is covered by "Per Channel": this framework models one
provider per channel type, not multiple competing providers behind the
same channel.)
"""

from __future__ import annotations

from shared_core.cache.manager import CacheManager
from shared_core.cache.ratelimit import RateLimitCache, RateLimitStatus
from shared_core.enums.notification_channel import NotificationChannel
from shared_core.notifications.constants import (
    DEFAULT_RATE_LIMIT_MAX_PER_CHANNEL,
    DEFAULT_RATE_LIMIT_MAX_PER_ORGANIZATION,
    DEFAULT_RATE_LIMIT_MAX_PER_USER,
    DEFAULT_RATE_LIMIT_WINDOW_SECONDS,
)

_GLOBAL_SCOPE = "global"


class NotificationRateLimiter:
    """Checks a notification against per-user/organization/channel/global limits.

    All four checks share the same underlying cache; a notification is
    only allowed once every configured scope allows it -- the first
    scope to reject wins, so no scope is checked unnecessarily once one
    has already failed.
    """

    def __init__(
        self,
        *,
        per_user: RateLimitCache,
        per_organization: RateLimitCache,
        per_channel: RateLimitCache,
        global_limit: RateLimitCache,
    ):
        self._per_user = per_user
        self._per_organization = per_organization
        self._per_channel = per_channel
        self._global_limit = global_limit

    async def check(
        self,
        *,
        user_id: str | None,
        organization_id: str | None,
        channel: NotificationChannel,
    ) -> RateLimitStatus:
        """Check every configured scope, returning the first rejection (or the last allow).

        Each scope's identifier is prefixed (``user:``/``org:``/
        ``channel:``) before being checked -- the four scopes use
        independent :class:`RateLimitCache` instances but share one
        underlying cache, so without a prefix a user ID and an
        organization ID with the same string value would collide onto
        the same counter.
        """
        status = await self._global_limit.check(_GLOBAL_SCOPE)
        if not status.allowed:
            return status
        status = await self._per_channel.check(f"channel:{channel.value}")
        if not status.allowed:
            return status
        if organization_id is not None:
            status = await self._per_organization.check(f"org:{organization_id}")
            if not status.allowed:
                return status
        if user_id is not None:
            status = await self._per_user.check(f"user:{user_id}")
            if not status.allowed:
                return status
        return status


def build_notification_rate_limiter(
    cache_manager: CacheManager,
    *,
    max_per_user: int = DEFAULT_RATE_LIMIT_MAX_PER_USER,
    max_per_organization: int = DEFAULT_RATE_LIMIT_MAX_PER_ORGANIZATION,
    max_per_channel: int = DEFAULT_RATE_LIMIT_MAX_PER_CHANNEL,
    max_global: int = DEFAULT_RATE_LIMIT_MAX_PER_ORGANIZATION,
    window_seconds: int = DEFAULT_RATE_LIMIT_WINDOW_SECONDS,
) -> NotificationRateLimiter:
    """Build a :class:`NotificationRateLimiter` with one :class:`RateLimitCache` per scope."""
    return NotificationRateLimiter(
        per_user=RateLimitCache(
            cache_manager, max_requests=max_per_user, window_seconds=window_seconds
        ),
        per_organization=RateLimitCache(
            cache_manager, max_requests=max_per_organization, window_seconds=window_seconds
        ),
        per_channel=RateLimitCache(
            cache_manager, max_requests=max_per_channel, window_seconds=window_seconds
        ),
        global_limit=RateLimitCache(
            cache_manager, max_requests=max_global, window_seconds=window_seconds
        ),
    )


__all__ = ["NotificationRateLimiter", "build_notification_rate_limiter"]
