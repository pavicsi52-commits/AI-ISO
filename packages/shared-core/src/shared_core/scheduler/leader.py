"""Leader election.

Per docs/026_Enterprise_Scheduler_Framework.md.txt "DISTRIBUTED
SCHEDULING": Leader Election, Failover, Split-Brain Prevention. Builds
leader election on top of :class:`shared_core.cache.locks.DistributedLock`
(already Redis-backed, already implements the token-checked
release/renew needed to keep ownership unambiguous) rather than a
bespoke consensus protocol -- exactly one node holds the
``scheduler:leader`` key at a time.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from redis.asyncio import Redis

from shared_core.cache.locks import DistributedLock
from shared_core.scheduler.constants import (
    DEFAULT_LEADER_LOCK_TTL_SECONDS,
    DEFAULT_LEADER_RENEW_INTERVAL_SECONDS,
)

_LEADER_LOCK_KEY = "scheduler:leader"

logger = logging.getLogger(__name__)


class LeaderElection:
    """Tracks and maintains this node's leadership of a scheduler cluster.

    Only the current leader performs cluster-wide duties (computing due
    jobs and enqueueing them); non-leader workers still execute jobs
    pulled from the queue but do not decide what's due, preventing every
    node from independently scheduling the same job ("Split-Brain
    Prevention"). If the leader stops renewing (crash, network
    partition), the lock's TTL expires and another node's next campaign
    picks up leadership -- "Failover".
    """

    def __init__(
        self,
        client: Redis,
        node_id: str,
        *,
        ttl_seconds: int = DEFAULT_LEADER_LOCK_TTL_SECONDS,
        renew_interval_seconds: float = DEFAULT_LEADER_RENEW_INTERVAL_SECONDS,
    ) -> None:
        self._lock = DistributedLock(client, _LEADER_LOCK_KEY, token=node_id)
        self._node_id = node_id
        self._ttl_seconds = ttl_seconds
        self._renew_interval_seconds = renew_interval_seconds
        self._is_leader = False
        self._task: asyncio.Task[None] | None = None

    @property
    def node_id(self) -> str:
        """This node's unique identifier, used as the lock's holder token."""
        return self._node_id

    @property
    def is_leader(self) -> bool:
        """Whether this node currently believes itself to be leader."""
        return self._is_leader

    async def campaign(self) -> bool:
        """Attempt a single leadership acquisition/renewal, returning the result.

        A node that already holds leadership renews its TTL (extending the
        lease); a node that does not tries a single, non-blocking
        acquisition, so a losing campaign never blocks the caller waiting
        on retries.
        """
        if self._is_leader:
            self._is_leader = await self._lock.renew(ttl_seconds=self._ttl_seconds)
        else:
            self._is_leader = await self._lock.acquire(ttl_seconds=self._ttl_seconds, max_retries=1)
        return self._is_leader

    async def resign(self) -> None:
        """Voluntarily give up leadership, if held (e.g. on graceful shutdown)."""
        if self._is_leader:
            await self._lock.release()
            self._is_leader = False

    async def start(self) -> None:
        """Start the background loop that repeatedly campaigns for leadership."""
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """Stop the background campaign loop and resign leadership."""
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        await self.resign()

    async def _run(self) -> None:
        while True:
            try:
                was_leader = self._is_leader
                now_leader = await self.campaign()
                if now_leader and not was_leader:
                    logger.info("Node %s acquired scheduler leadership.", self._node_id)
                elif was_leader and not now_leader:
                    logger.warning("Node %s lost scheduler leadership.", self._node_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Leader election campaign failed for node %s.", self._node_id)
            await asyncio.sleep(self._renew_interval_seconds)


async def cluster_has_leader(client: Redis) -> bool:
    """Whether any node in the cluster currently holds scheduler leadership.

    Queried fresh from Redis rather than any single node's own
    (potentially stale) :attr:`LeaderElection.is_leader` -- used by
    :mod:`shared_core.scheduler.health` to report cluster-wide "Leader
    Status" regardless of which node is asking.
    """
    return bool(await client.exists(_LEADER_LOCK_KEY))


__all__ = ["LeaderElection", "cluster_has_leader"]
