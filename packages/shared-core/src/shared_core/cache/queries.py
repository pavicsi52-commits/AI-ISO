"""Query Cache.

Per docs/019_Enterprise_Cache_Framework.md.txt "QUERY CACHE": Cache Search
Results, Pagination, Filtering, Sorting, Metadata. "Automatic invalidation
after updates."

Caches an arbitrary query's result set keyed by a stable hash of its
parameters (search term, filters, sort, page) under a named "collection",
so every cached result for that collection can be invalidated together
after a write via :meth:`QueryCache.invalidate_all` -- without this
framework depending on :mod:`shared_core.database`'s pagination/filtering
types directly (this package must stay database-framework-agnostic).
"""

from __future__ import annotations

from typing import Any

from shared_core.cache.constants import DEFAULT_TTL_SECONDS
from shared_core.cache.helpers import stable_query_hash
from shared_core.cache.keys import build_cache_key, build_pattern
from shared_core.cache.manager import CacheManager


class QueryCache:
    """Caches query results (search/pagination/filter/sort/metadata) per named collection."""

    def __init__(
        self,
        cache: CacheManager,
        *,
        collection: str,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ) -> None:
        self._cache = cache
        self._collection = collection
        self._ttl_seconds = ttl_seconds

    def _key(self, **params: Any) -> str:
        return build_cache_key("query", self._collection, stable_query_hash(**params))

    async def get(self, **params: Any) -> Any | None:
        """Return the cached result for this exact set of query parameters, or ``None``."""
        return await self._cache.get(self._key(**params))

    async def set(self, result: Any, **params: Any) -> None:
        """Cache *result* under this exact set of query parameters."""
        await self._cache.set(self._key(**params), result, ttl_seconds=self._ttl_seconds)

    async def invalidate_all(self) -> int:
        """Invalidate every cached query result for this collection.

        Call after any write to the underlying collection -- "Automatic
        invalidation after updates" (docs/019).
        """
        return await self._cache.clear(build_pattern("query", self._collection, "*"))


__all__ = ["QueryCache"]
