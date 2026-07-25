"""Automatic failover.

Per docs/026_Enterprise_Scheduler_Framework.md.txt "DISTRIBUTED
SCHEDULING": Automatic Failover; "HIGH AVAILABILITY": Scheduler
Failover, Worker Recovery, Job Recovery, Duplicate Prevention. Watches
:class:`shared_core.scheduler.heartbeat.HeartbeatRegistry` for nodes
that stop heartbeating and invokes a caller-supplied recovery callback
for each -- kept decoupled from job storage/queueing (built in later
modules of this package) so this module only owns detecting failure,
not what recovery means for a particular job store. "Leader
Re-election" is handled by :mod:`shared_core.scheduler.leader` itself
(a fresh campaign after the incumbent's lease lapses); this module
covers *worker* (non-leader) failure.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable

from shared_core.scheduler.constants import DEFAULT_HEARTBEAT_INTERVAL_SECONDS
from shared_core.scheduler.heartbeat import HeartbeatRegistry

logger = logging.getLogger(__name__)

NodeFailureHandler = Callable[[str], Awaitable[None]]


class FailoverCoordinator:
    """Detects nodes that stopped heartbeating and triggers recovery for each.

    A node is considered failed the first time it no longer appears in
    :meth:`~shared_core.scheduler.heartbeat.HeartbeatRegistry.list_active_nodes`
    after having previously been observed -- each such transition fires
    *on_node_failed* exactly once ("Duplicate Prevention"), letting the
    caller reassign that node's in-flight jobs ("Job Recovery"/"Worker
    Recovery") without doing it twice for the same failure.
    """

    def __init__(
        self,
        registry: HeartbeatRegistry,
        on_node_failed: NodeFailureHandler,
        *,
        poll_interval_seconds: float = DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
    ) -> None:
        self._registry = registry
        self._on_node_failed = on_node_failed
        self._poll_interval_seconds = poll_interval_seconds
        self._known_node_ids: set[str] = set()
        self._task: asyncio.Task[None] | None = None

    async def check_once(self) -> list[str]:
        """Run a single detection pass, returning any newly failed node ids."""
        active_ids = {node.node_id for node in await self._registry.list_active_nodes()}
        failed_ids = self._known_node_ids - active_ids
        self._known_node_ids = active_ids
        for node_id in sorted(failed_ids):
            try:
                await self._on_node_failed(node_id)
            except Exception:
                logger.exception("Failover recovery callback failed for node %s.", node_id)
        return sorted(failed_ids)

    async def start(self) -> None:
        """Start the background detection loop."""
        if self._task is not None:
            return
        self._known_node_ids = {node.node_id for node in await self._registry.list_active_nodes()}
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """Stop the background detection loop."""
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self._poll_interval_seconds)
            await self.check_once()


__all__ = ["FailoverCoordinator", "NodeFailureHandler"]
