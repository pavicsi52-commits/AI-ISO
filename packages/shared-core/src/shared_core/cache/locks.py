"""Distributed locks.

Per docs/019_Enterprise_Cache_Framework.md.txt "DISTRIBUTED LOCKS":
Acquire, Release, Timeout, Renew, Retry, Deadlock Protection. "Use Redis
Redlock principles." Renamed from Prompt 012's ``lock.py`` to match this
prompt's directory structure -- the only import path that changed
(``shared_core.cache.lock`` -> ``shared_core.cache.locks``).

:class:`DistributedLock` is the single-node lock (sufficient for a
standalone/Sentinel/Cluster deployment backed by one logical Redis);
:class:`Redlock` implements the actual multi-node Redlock algorithm for
callers who hold independent Redis instances and need quorum-based safety
against a single node's failure.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager

from redis.asyncio import Redis
from redis.exceptions import WatchError

from shared_core.cache.constants import (
    DEFAULT_LOCK_CLOCK_DRIFT_FACTOR,
    DEFAULT_LOCK_MAX_RETRIES,
    DEFAULT_LOCK_RETRY_DELAY_SECONDS,
    DEFAULT_LOCK_TTL_SECONDS,
)
from shared_core.cache.exceptions import LockAcquisitionFailedError


class DistributedLock:
    """A Redis-backed mutual-exclusion lock identified by a cache key."""

    def __init__(self, client: Redis, key: str, *, token: str | None = None) -> None:
        self._client = client
        self._key = key
        self._token = token or str(uuid.uuid4())

    @property
    def token(self) -> str:
        """This lock instance's unique holder token."""
        return self._token

    async def acquire(
        self,
        *,
        ttl_seconds: int = DEFAULT_LOCK_TTL_SECONDS,
        max_retries: int = DEFAULT_LOCK_MAX_RETRIES,
        retry_delay_seconds: float = DEFAULT_LOCK_RETRY_DELAY_SECONDS,
    ) -> bool:
        """Attempt to acquire the lock, retrying until ``max_retries`` is exhausted."""
        for _ in range(max_retries):
            acquired = await self._client.set(self._key, self._token, nx=True, ex=ttl_seconds)
            if acquired:
                return True
            await asyncio.sleep(retry_delay_seconds)
        return False

    async def release(self) -> None:
        """Release the lock, but only if still held by this instance's token.

        Uses an optimistic ``WATCH``/``MULTI``/``EXEC`` transaction: the
        delete only commits if no one else changed the key between the
        read and the write, so a lock can never delete a key it no longer
        owns (e.g. one that expired and was re-acquired by someone else) --
        "Deadlock Protection".
        """
        async with self._client.pipeline(transaction=True) as pipe:
            while True:
                try:
                    await pipe.watch(self._key)
                    current_value = await pipe.get(self._key)
                    if isinstance(current_value, bytes):
                        current_value = current_value.decode("utf-8")
                    if current_value != self._token:
                        await pipe.unwatch()  # type: ignore[no-untyped-call]
                        return
                    pipe.multi()  # type: ignore[no-untyped-call]
                    pipe.delete(self._key)
                    await pipe.execute()
                    return
                except WatchError:
                    continue

    async def renew(self, *, ttl_seconds: int = DEFAULT_LOCK_TTL_SECONDS) -> bool:
        """Extend this lock's TTL, but only if still held by this instance's token.

        A crashed holder never gets its lock "resurrected" by a stray
        renewal -- the same ownership check as :meth:`release` gates the
        extension, so renewal can only ever prolong a lock this instance
        actually still holds.
        """
        async with self._client.pipeline(transaction=True) as pipe:
            while True:
                try:
                    await pipe.watch(self._key)
                    current_value = await pipe.get(self._key)
                    if isinstance(current_value, bytes):
                        current_value = current_value.decode("utf-8")
                    if current_value != self._token:
                        await pipe.unwatch()  # type: ignore[no-untyped-call]
                        return False
                    pipe.multi()  # type: ignore[no-untyped-call]
                    pipe.expire(self._key, ttl_seconds)
                    await pipe.execute()
                    return True
                except WatchError:
                    continue


@asynccontextmanager
async def distributed_lock(
    client: Redis, key: str, *, ttl_seconds: int = DEFAULT_LOCK_TTL_SECONDS
) -> AsyncIterator[None]:
    """Acquire a distributed lock for the duration of the context block.

    Raises:
        LockAcquisitionFailedError: If the lock could not be acquired.
    """
    lock = DistributedLock(client, key)
    if not await lock.acquire(ttl_seconds=ttl_seconds):
        raise LockAcquisitionFailedError(f"Could not acquire lock '{key}'.")
    try:
        yield
    finally:
        await lock.release()


class Redlock:
    """Multi-node distributed lock following the Redlock algorithm.

    Acquires the same lock key against every client in *clients*
    independently; the lock is considered held only once a majority
    (quorum) of nodes granted it, with the elapsed acquisition time and a
    small clock-drift safety margin subtracted from the claimed validity
    window -- "Use Redis Redlock principles" (docs/019).
    """

    def __init__(self, clients: Sequence[Redis], key: str) -> None:
        if not clients:
            raise ValueError("Redlock requires at least one Redis client.")
        self._clients = list(clients)
        self._key = key
        self._token = str(uuid.uuid4())
        self._quorum = len(self._clients) // 2 + 1

    @property
    def token(self) -> str:
        """This Redlock instance's unique holder token, shared across every node."""
        return self._token

    async def acquire(self, *, ttl_seconds: int = DEFAULT_LOCK_TTL_SECONDS) -> bool:
        """Attempt to acquire the lock on a quorum of nodes.

        A node that's unreachable or errors is simply not counted toward
        the quorum -- one bad node must never block acquisition when the
        rest agree. If quorum isn't reached (or the elapsed time already
        ate into the TTL's validity), any partial grants are released and
        this returns ``False`` rather than leaving a half-acquired lock.
        """
        start = time.monotonic()
        granted = 0
        for client in self._clients:
            try:
                lock = DistributedLock(client, self._key, token=self._token)
                if await lock.acquire(ttl_seconds=ttl_seconds, max_retries=1):
                    granted += 1
            except Exception:
                continue

        elapsed_seconds = time.monotonic() - start
        drift_seconds = ttl_seconds * DEFAULT_LOCK_CLOCK_DRIFT_FACTOR
        remaining_validity_seconds = ttl_seconds - elapsed_seconds - drift_seconds

        if granted >= self._quorum and remaining_validity_seconds > 0:
            return True
        await self.release()
        return False

    async def release(self) -> None:
        """Release the lock on every node that might be holding it."""
        for client in self._clients:
            try:
                await DistributedLock(client, self._key, token=self._token).release()
            except Exception:
                continue


@asynccontextmanager
async def redlock(
    clients: Sequence[Redis], key: str, *, ttl_seconds: int = DEFAULT_LOCK_TTL_SECONDS
) -> AsyncIterator[None]:
    """Acquire a :class:`Redlock` for the duration of the context block.

    Raises:
        LockAcquisitionFailedError: If quorum could not be reached.
    """
    lock = Redlock(clients, key)
    if not await lock.acquire(ttl_seconds=ttl_seconds):
        raise LockAcquisitionFailedError(f"Could not acquire Redlock '{key}' on a quorum of nodes.")
    try:
        yield
    finally:
        await lock.release()


__all__ = ["DistributedLock", "Redlock", "distributed_lock", "redlock"]
