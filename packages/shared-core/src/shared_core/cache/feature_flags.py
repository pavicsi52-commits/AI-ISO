"""Feature Flag Cache.

Per docs/019_Enterprise_Cache_Framework.md.txt "FEATURE FLAGS": Global
Flags, Organization Flags, Project Flags, User Flags, Rollout Percentage,
Expiration, Audit.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from shared_core.cache.constants import DEFAULT_FEATURE_FLAG_TTL_SECONDS
from shared_core.cache.keys import build_cache_key
from shared_core.cache.manager import CacheManager
from shared_core.logging import get_logger

logger = get_logger("shared_core.cache.feature_flags")

_FULL_ROLLOUT_PERCENTAGE = 100.0
_NO_ROLLOUT_PERCENTAGE = 0.0
_ROLLOUT_BUCKET_COUNT = 100


class FeatureFlagScope(StrEnum):
    """Which level a feature flag is evaluated at."""

    GLOBAL = "global"
    ORGANIZATION = "organization"
    PROJECT = "project"
    USER = "user"


@dataclass(frozen=True, slots=True)
class FeatureFlag:
    """A feature flag's stored state."""

    name: str
    enabled: bool
    rollout_percentage: float = _FULL_ROLLOUT_PERCENTAGE
    scope: FeatureFlagScope = FeatureFlagScope.GLOBAL


class FeatureFlagCache:
    """Feature flag storage, keyed by ``(scope, scope_id, flag name)``."""

    def __init__(
        self, cache: CacheManager, *, ttl_seconds: int = DEFAULT_FEATURE_FLAG_TTL_SECONDS
    ) -> None:
        self._cache = cache
        self._ttl_seconds = ttl_seconds

    def _key(self, scope: FeatureFlagScope, scope_id: str, name: str) -> str:
        return build_cache_key("feature_flag", scope.value, scope_id, name)

    async def set_flag(
        self, flag: FeatureFlag, *, scope_id: str = "global", actor_id: str | None = None
    ) -> None:
        """Store a flag's state. Emits an audit log entry ("Audit", docs/019)."""
        await self._cache.set(
            self._key(flag.scope, scope_id, flag.name),
            {"enabled": flag.enabled, "rollout_percentage": flag.rollout_percentage},
            ttl_seconds=self._ttl_seconds,
        )
        logger.audit(
            "feature_flag_changed",
            actor_id=actor_id,
            resource=flag.name,
            scope=flag.scope.value,
            scope_id=scope_id,
            enabled=flag.enabled,
            rollout_percentage=flag.rollout_percentage,
        )

    async def get_flag(
        self,
        name: str,
        *,
        scope: FeatureFlagScope = FeatureFlagScope.GLOBAL,
        scope_id: str = "global",
    ) -> FeatureFlag | None:
        """Return a flag's stored state, or ``None`` if never set (or expired)."""
        data: dict[str, Any] | None = await self._cache.get(self._key(scope, scope_id, name))
        if data is None:
            return None
        return FeatureFlag(
            name=name,
            enabled=data["enabled"],
            rollout_percentage=data["rollout_percentage"],
            scope=scope,
        )

    async def is_enabled(
        self,
        name: str,
        *,
        scope: FeatureFlagScope = FeatureFlagScope.GLOBAL,
        scope_id: str = "global",
        rollout_key: str | None = None,
    ) -> bool:
        """Return whether *name* is enabled for this scope, honoring rollout percentage.

        *rollout_key* (e.g. a user ID) determines which side of the
        rollout percentage a given caller falls on -- deterministic, so
        the same key always gets the same answer for a given percentage,
        rather than flapping between calls.
        """
        flag = await self.get_flag(name, scope=scope, scope_id=scope_id)
        if flag is None or not flag.enabled:
            return False
        if flag.rollout_percentage >= _FULL_ROLLOUT_PERCENTAGE:
            return True
        if flag.rollout_percentage <= _NO_ROLLOUT_PERCENTAGE:
            return False
        bucket_source = rollout_key or scope_id
        digest = hashlib.sha256(f"{name}:{bucket_source}".encode()).hexdigest()
        bucket = int(digest, 16) % _ROLLOUT_BUCKET_COUNT
        return bucket < flag.rollout_percentage

    async def delete_flag(
        self,
        name: str,
        *,
        scope: FeatureFlagScope = FeatureFlagScope.GLOBAL,
        scope_id: str = "global",
    ) -> None:
        """Delete a flag's stored state."""
        await self._cache.delete(self._key(scope, scope_id, name))


__all__ = ["FeatureFlag", "FeatureFlagCache", "FeatureFlagScope"]
