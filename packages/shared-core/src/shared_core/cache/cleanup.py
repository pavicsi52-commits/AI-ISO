"""Cache invalidation.

Per docs/019_Enterprise_Cache_Framework.md.txt "CACHE INVALIDATION":
Manual, Automatic, Event Driven, TTL, Dependency Based, Pattern Based,
Bulk Invalidation.

TTL-based invalidation needs no code here -- it's automatic expiration,
already covered by every ``set()`` call's TTL. This module covers
everything that must be *triggered*: an explicit call ("Manual"), a
decorator-driven post-write eviction ("Automatic" --
:mod:`shared_core.cache.decorators`), a domain event ("Event Driven"), a
dependency graph between cache keys and the data they were derived from
("Dependency Based"), and glob-pattern/multi-key deletes ("Pattern Based"
/ "Bulk Invalidation").
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field

from shared_core.cache.keys import build_cache_key
from shared_core.cache.manager import CacheManager


async def invalidate_key(cache: CacheManager, key: str) -> bool:
    """Manually invalidate one key."""
    return await cache.delete(key)


async def invalidate_keys(cache: CacheManager, keys: Sequence[str]) -> int:
    """Manually invalidate many keys at once ("Bulk Invalidation")."""
    return await cache.bulk_delete(keys)


async def invalidate_pattern(cache: CacheManager, pattern: str) -> int:
    """Invalidate every key matching a glob pattern ("Pattern Based")."""
    return await cache.clear(pattern)


class DependencyTracker:
    """Tracks which cache keys depend on which "tags", for dependency-based invalidation.

    Example: a query-cache result tagged with ``"asset:123"`` gets
    invalidated automatically whenever :meth:`invalidate_tag` is called
    for that tag after the asset is written -- callers never have to know
    every cache key that happened to read it.
    """

    def __init__(self, cache: CacheManager) -> None:
        self._cache = cache

    def _tag_key(self, tag: str) -> str:
        return build_cache_key("tag", tag)

    async def track(self, tag: str, cache_key: str) -> None:
        """Record that *cache_key*'s value depends on *tag*."""
        members: list[str] = await self._cache.get(self._tag_key(tag)) or []
        if cache_key not in members:
            members.append(cache_key)
            await self._cache.set(self._tag_key(tag), members)

    async def invalidate_tag(self, tag: str) -> int:
        """Delete every cache key tracked under *tag*, then the tracking record itself."""
        members: list[str] = await self._cache.get(self._tag_key(tag)) or []
        deleted = await self._cache.bulk_delete(members) if members else 0
        await self._cache.delete(self._tag_key(tag))
        return deleted


EventHandler = Callable[[], Awaitable[None]]


@dataclass(slots=True)
class EventInvalidator:
    """Maps domain event names to the cache-invalidation actions they trigger ("Event Driven").

    Registered handlers are plain callables so this stays decoupled from
    any specific event-bus implementation (this framework must not
    implement business logic -- docs/019 "DO NOT IMPLEMENT"); a service's
    own event consumer calls :meth:`handle` from its event-bus
    subscription.
    """

    _handlers: dict[str, list[EventHandler]] = field(default_factory=dict)

    def on(self, event_name: str, handler: EventHandler) -> None:
        """Register *handler* to run when *event_name* is handled."""
        self._handlers.setdefault(event_name, []).append(handler)

    async def handle(self, event_name: str) -> int:
        """Run every handler registered for *event_name*. Returns the count run."""
        handlers = self._handlers.get(event_name, [])
        for handler in handlers:
            await handler()
        return len(handlers)


__all__ = [
    "DependencyTracker",
    "EventInvalidator",
    "invalidate_key",
    "invalidate_keys",
    "invalidate_pattern",
]
