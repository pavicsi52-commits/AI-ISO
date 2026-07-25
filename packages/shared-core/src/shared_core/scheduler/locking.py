"""Distributed job locking.

Per docs/026_Enterprise_Scheduler_Framework.md.txt "DISTRIBUTED
SCHEDULING": Distributed Locks. Reuses
:class:`shared_core.cache.locks.DistributedLock` directly (Redis-backed,
Redlock-principled, already implements Acquire/Release/Timeout/Renew/
Retry/Deadlock Protection per docs/019) rather than reimplementing
distributed locking a second time -- this module only names the
convention for a job's lock key and wraps acquisition in the
"Exclusive Execution" context manager
:mod:`shared_core.scheduler.executor` needs.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from redis.asyncio import Redis

from shared_core.cache.locks import DistributedLock
from shared_core.scheduler.constants import DEFAULT_JOB_LOCK_TTL_SECONDS


def job_lock_key(job_id: str) -> str:
    """The Redis key used to hold a job's exclusive-execution lock."""
    return f"scheduler:job-lock:{job_id}"


@asynccontextmanager
async def exclusive_job_execution(
    client: Redis, job_id: str, *, ttl_seconds: int = DEFAULT_JOB_LOCK_TTL_SECONDS
) -> AsyncIterator[bool]:
    """Attempt to acquire *job_id*'s exclusive-execution lock ("Exclusive Execution").

    Yields ``True`` if the lock was acquired (the caller should run the
    job) or ``False`` if not (another worker already holds it -- the
    caller should skip this run, not treat it as a failure). Always
    releases on exit if it was acquired, "Prevent Duplicate Delivery"
    for the common case of two workers waking up for the same due job
    at once.
    """
    lock = DistributedLock(client, job_lock_key(job_id))
    acquired = await lock.acquire(ttl_seconds=ttl_seconds, max_retries=1)
    try:
        yield acquired
    finally:
        if acquired:
            await lock.release()


__all__ = ["exclusive_job_execution", "job_lock_key"]
