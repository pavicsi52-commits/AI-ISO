"""Cache manager.

The only place any AI-IOS service talks to Redis directly, per
docs/019_Enterprise_Cache_Framework.md.txt "OBJECTIVE": "No service shall
communicate directly with Redis. All cache operations must go through this
framework." Implements every docs/019 "CACHE MANAGER" operation (Set, Get,
Delete, Exists, Increment, Decrement, Expire, Persist, Touch, Clear, Bulk
Set, Bulk Get, Bulk Delete) with automatic serialize/compress/encrypt on
write and the inverse on read.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from redis.asyncio import Redis

from shared_core.cache.compression import CompressionAlgorithm, compress, decompress
from shared_core.cache.encryption import decrypt_value, encrypt_value
from shared_core.cache.exceptions import CacheEncryptionError
from shared_core.cache.serializer import deserialize, serialize
from shared_core.cache.settings import CacheSettings
from shared_core.cache.statistics import CacheStatistics
from shared_core.cache.ttl import resolve_ttl, validate_ttl


class CacheManager:
    """The framework's single entry point for every cache operation.

    Cache is never the source of truth — failures here should degrade
    gracefully in calling code, never corrupt business data (docs/019
    "CACHE PHILOSOPHY").
    """

    def __init__(
        self,
        client: Redis,
        *,
        settings: CacheSettings | None = None,
        statistics: CacheStatistics | None = None,
    ) -> None:
        self._client = client
        self._settings = settings or CacheSettings()
        self._stats = statistics or CacheStatistics()

    @property
    def statistics(self) -> CacheStatistics:
        """This manager's hit/miss/latency counters (docs/019 "METRICS")."""
        return self._stats

    async def get(self, key: str) -> Any | None:
        """Return the deserialized value for ``key``, or ``None`` if absent."""
        raw = await self._client.get(key)
        if raw is None:
            self._stats.record_miss()
            return None
        self._stats.record_hit()
        # Every client this framework constructs uses decode_responses=False,
        # so `raw` is always bytes at runtime; the client stub's return type
        # is a wider bytes|str union covering both client configurations.
        return self._decode(raw)  # type: ignore[arg-type]

    async def set(
        self,
        key: str,
        value: Any,
        *,
        ttl_seconds: int | None = None,
    ) -> None:
        """Set ``key`` to the serialized/compressed/encrypted ``value`` with a TTL."""
        resolved_ttl = resolve_ttl(ttl_seconds, default=self._settings.default_ttl_seconds)
        payload = self._encode(value)
        if resolved_ttl is None:
            await self._client.set(key, payload)
        else:
            await self._client.set(key, payload, ex=resolved_ttl)
        self._stats.record_set()

    async def delete(self, key: str) -> bool:
        """Delete ``key``. Returns whether a key was actually removed."""
        deleted = bool(await self._client.delete(key))
        if deleted:
            self._stats.record_delete()
        return deleted

    async def exists(self, key: str) -> bool:
        """Return whether ``key`` exists."""
        return bool(await self._client.exists(key))

    async def increment(self, key: str, *, amount: int = 1) -> int:
        """Atomically increment ``key`` by ``amount`` and return the new value."""
        return int(await self._client.incrby(key, amount))

    async def decrement(self, key: str, *, amount: int = 1) -> int:
        """Atomically decrement ``key`` by ``amount`` and return the new value."""
        return int(await self._client.decrby(key, amount))

    async def expire(self, key: str, ttl_seconds: int) -> bool:
        """Set a new TTL on an existing key. Returns whether the key existed."""
        validate_ttl(ttl_seconds)
        return bool(await self._client.expire(key, ttl_seconds))

    async def persist(self, key: str) -> bool:
        """Remove ``key``'s TTL, making it permanent until explicitly deleted."""
        return bool(await self._client.persist(key))

    async def touch(self, key: str, *, ttl_seconds: int | None = None) -> bool:
        """Refresh ``key``'s expiration without changing its value ("Sliding TTL").

        If *ttl_seconds* is given, sets that as the new TTL (used for
        idle-timeout-style sliding expiration); otherwise resets the
        key's last-accessed time via Redis's own ``TOUCH``.
        """
        if ttl_seconds is not None:
            return await self.expire(key, ttl_seconds)
        return bool(await self._client.touch(key))

    async def clear(self, pattern: str) -> int:
        """Delete every key matching *pattern* (a Redis ``SCAN``-style glob). Returns the count."""
        keys = [key async for key in self._client.scan_iter(match=pattern)]
        if not keys:
            return 0
        return int(await self._client.delete(*keys))

    async def clear_prefix(self, prefix: str) -> int:
        """Delete every key starting with ``prefix``. Returns the count deleted."""
        return await self.clear(f"{prefix}*")

    async def bulk_set(self, items: dict[str, Any], *, ttl_seconds: int | None = None) -> None:
        """Set many keys in a single pipelined round trip."""
        if not items:
            return
        resolved_ttl = resolve_ttl(ttl_seconds, default=self._settings.default_ttl_seconds)
        async with self._client.pipeline(transaction=False) as pipe:
            for key, value in items.items():
                payload = self._encode(value)
                if resolved_ttl is None:
                    pipe.set(key, payload)
                else:
                    pipe.set(key, payload, ex=resolved_ttl)
            await pipe.execute()
        for _ in items:
            self._stats.record_set()

    async def bulk_get(self, keys: Sequence[str]) -> dict[str, Any | None]:
        """Return ``{key: value}`` for every key in *keys*, in one round trip.

        Keys with no cached value map to ``None`` rather than being omitted
        — the result always has exactly one entry per requested key.
        """
        if not keys:
            return {}
        raw_values = await self._client.mget(keys)
        result: dict[str, Any | None] = {}
        for key, raw in zip(keys, raw_values, strict=True):
            if raw is None:
                self._stats.record_miss()
                result[key] = None
            else:
                self._stats.record_hit()
                result[key] = self._decode(raw)  # type: ignore[arg-type]  # see get()
        return result

    async def bulk_delete(self, keys: Sequence[str]) -> int:
        """Delete many keys in a single round trip. Returns the count actually removed."""
        if not keys:
            return 0
        deleted = int(await self._client.delete(*keys))
        for _ in range(deleted):
            self._stats.record_delete()
        return deleted

    def _encode(self, value: Any) -> bytes:
        data = serialize(value, fmt=self._settings.serialization_format)
        algorithm = (
            CompressionAlgorithm.ZSTD
            if self._settings.compression_enabled
            else CompressionAlgorithm.NONE
        )
        data = compress(
            data, algorithm=algorithm, threshold_bytes=self._settings.compression_threshold_bytes
        )
        if self._settings.encryption_enabled:
            if not self._settings.encryption_key:
                raise CacheEncryptionError(
                    "CacheSettings.encryption_enabled is True but no encryption_key is configured."
                )
            data = encrypt_value(data, key=self._settings.encryption_key)
        return data

    def _decode(self, raw: bytes) -> Any:
        data = raw
        if self._settings.encryption_enabled:
            if not self._settings.encryption_key:
                raise CacheEncryptionError(
                    "CacheSettings.encryption_enabled is True but no encryption_key is configured."
                )
            data = decrypt_value(data, key=self._settings.encryption_key)
        data = decompress(data)
        return deserialize(data, fmt=self._settings.serialization_format)


__all__ = ["CacheManager"]
