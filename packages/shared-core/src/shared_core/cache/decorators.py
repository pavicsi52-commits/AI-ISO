"""Cache decorators.

Per docs/019_Enterprise_Cache_Framework.md.txt "CACHE DECORATORS": ``@cache``,
``@invalidate``, ``@cacheable``, ``@evict``, ``@refresh``,
``@distributed_lock``, ``@rate_limit``.

Imported from this submodule directly (``from shared_core.cache.decorators
import ...``) rather than assumed to all be re-exported at the package
root: :func:`distributed_lock` here (the decorator) shares its name with
:func:`shared_core.cache.locks.distributed_lock` (the async context
manager) -- importing both into the same namespace would have the second
import silently shadow the first. ``cached``/``cache_evict`` remain
re-exported at :mod:`shared_core.cache`'s root as the Prompt 012 baseline
always was; every name introduced by this prompt lives here only.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any

from redis.asyncio import Redis

from shared_core.cache.constants import DEFAULT_LOCK_TTL_SECONDS, DEFAULT_TTL_SECONDS
from shared_core.cache.keys import build_cache_key
from shared_core.cache.locks import distributed_lock as _distributed_lock_context
from shared_core.cache.manager import CacheManager
from shared_core.cache.ratelimit import RateLimitCache
from shared_core.exceptions.rate_limit import RateLimitError
from shared_core.helpers.hash_helper import stable_hash

KeyFunc = Callable[..., str]
_AsyncFunc = Callable[..., Awaitable[Any]]


def _default_key_func(key_prefix: str) -> KeyFunc:
    def _build(*args: Any, **kwargs: Any) -> str:
        arg_parts = (str(a) for a in args)
        kwarg_parts = (f"{k}={v}" for k, v in kwargs.items())
        arg_hash = stable_hash(*arg_parts, *kwarg_parts)
        return build_cache_key(key_prefix, arg_hash)

    return _build


def cache(
    cache_manager: CacheManager, *, key_fn: KeyFunc, ttl_seconds: int = DEFAULT_TTL_SECONDS
) -> Callable[[_AsyncFunc], _AsyncFunc]:
    """Cache an async function's result under an explicit, caller-built key.

    Unlike :func:`cached` (which hashes the raw call arguments into an
    opaque key), *key_fn* receives the same arguments and returns a
    meaningful cache key -- e.g. ``lambda asset_id: asset_key(asset_id)``
    -- so the key is inspectable/matchable by other tools (invalidation,
    debugging) without needing to know the hash.
    """

    def decorator(func: _AsyncFunc) -> _AsyncFunc:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            key = key_fn(*args, **kwargs)
            cached_value = await cache_manager.get(key)
            if cached_value is not None:
                return cached_value
            result = await func(*args, **kwargs)
            await cache_manager.set(key, result, ttl_seconds=ttl_seconds)
            return result

        return wrapper

    return decorator


def cached(
    cache_manager: CacheManager, *, key_prefix: str, ttl_seconds: int = DEFAULT_TTL_SECONDS
) -> Callable[[_AsyncFunc], _AsyncFunc]:
    """Cache the JSON-serializable result of an async function.

    The cache key is derived from ``key_prefix`` plus a stable hash of the
    function's arguments, so calls with different arguments don't collide.
    """
    return cache(cache_manager, key_fn=_default_key_func(key_prefix), ttl_seconds=ttl_seconds)


#: Per docs/019 "CACHE DECORATORS": both names refer to the same
#: read-through-cache behavior.
cacheable = cached


def cache_evict(
    cache_manager: CacheManager, *, key_prefix: str
) -> Callable[[_AsyncFunc], _AsyncFunc]:
    """Evict every cache key under ``key_prefix`` after the wrapped function runs."""

    def decorator(func: _AsyncFunc) -> _AsyncFunc:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            result = await func(*args, **kwargs)
            await cache_manager.clear_prefix(build_cache_key(key_prefix))
            return result

        return wrapper

    return decorator


#: Per docs/019 "CACHE DECORATORS": this prompt's name for the same
#: bulk, prefix-based eviction behavior.
evict = cache_evict


def invalidate(
    cache_manager: CacheManager, *, key_fn: KeyFunc
) -> Callable[[_AsyncFunc], _AsyncFunc]:
    """Delete one specific cache key (from the call arguments) after the wrapped function runs.

    Unlike :func:`evict` (bulk, prefix-based), this targets exactly the
    key a matching :func:`cache`/:func:`cached` call would have used --
    for invalidating a single known entity after it's updated.
    """

    def decorator(func: _AsyncFunc) -> _AsyncFunc:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            result = await func(*args, **kwargs)
            await cache_manager.delete(key_fn(*args, **kwargs))
            return result

        return wrapper

    return decorator


def refresh(
    cache_manager: CacheManager, *, key_prefix: str, ttl_seconds: int = DEFAULT_TTL_SECONDS
) -> Callable[[_AsyncFunc], _AsyncFunc]:
    """Always call the wrapped function and overwrite the cache, ignoring any existing value.

    For call sites that need a guaranteed-fresh read while still
    populating the cache for the *next* caller (e.g. a manual "refresh
    now" action) -- unlike :func:`cached`, this never returns a
    previously-cached value.
    """
    key_fn = _default_key_func(key_prefix)

    def decorator(func: _AsyncFunc) -> _AsyncFunc:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            result = await func(*args, **kwargs)
            await cache_manager.set(key_fn(*args, **kwargs), result, ttl_seconds=ttl_seconds)
            return result

        return wrapper

    return decorator


def distributed_lock(
    client: Redis, *, key_fn: KeyFunc, ttl_seconds: int = DEFAULT_LOCK_TTL_SECONDS
) -> Callable[[_AsyncFunc], _AsyncFunc]:
    """Run the wrapped function only while holding a distributed lock built from its arguments."""

    def decorator(func: _AsyncFunc) -> _AsyncFunc:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            key = key_fn(*args, **kwargs)
            async with _distributed_lock_context(client, key, ttl_seconds=ttl_seconds):
                return await func(*args, **kwargs)

        return wrapper

    return decorator


def rate_limit(
    rate_limiter: RateLimitCache, *, key_fn: KeyFunc
) -> Callable[[_AsyncFunc], _AsyncFunc]:
    """Enforce a rate limit (built from the call arguments) before running the wrapped function.

    Raises:
        RateLimitError: If the caller has exceeded its limit.
    """

    def decorator(func: _AsyncFunc) -> _AsyncFunc:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            status = await rate_limiter.check(key_fn(*args, **kwargs))
            if not status.allowed:
                raise RateLimitError(
                    f"Rate limit exceeded. Retry after {status.retry_after_seconds}s."
                )
            return await func(*args, **kwargs)

        return wrapper

    return decorator


__all__ = [
    "cache",
    "cache_evict",
    "cacheable",
    "cached",
    "distributed_lock",
    "evict",
    "invalidate",
    "rate_limit",
    "refresh",
]
