"""Worker heartbeat tracking.

Per docs/026_Enterprise_Scheduler_Framework.md.txt "DISTRIBUTED
SCHEDULING": Worker Coordination, Node Registration, Heartbeat. Each
node periodically refreshes a TTL'd Redis key naming itself as alive;
Redis's own expiry is the failure detector -- a node that stops
heartbeating simply falls out of :meth:`HeartbeatRegistry.list_active_nodes`
once its key expires, with no separate reaper process required.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from dataclasses import dataclass

from redis.asyncio import Redis

from shared_core.scheduler.constants import (
    DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
    DEFAULT_HEARTBEAT_TIMEOUT_SECONDS,
)

_HEARTBEAT_KEY_PREFIX = "scheduler:heartbeat:"


@dataclass(frozen=True, slots=True)
class NodeHeartbeat:
    """A single node's most recently recorded heartbeat."""

    node_id: str
    last_seen: float


class HeartbeatRegistry:
    """Tracks which scheduler nodes are currently alive, via TTL'd Redis keys."""

    def __init__(
        self,
        client: Redis,
        *,
        timeout_seconds: float = DEFAULT_HEARTBEAT_TIMEOUT_SECONDS,
    ) -> None:
        self._client = client
        self._timeout_seconds = timeout_seconds

    async def beat(self, node_id: str) -> None:
        """Record that *node_id* is alive, refreshing its TTL ("Heartbeat")."""
        key = f"{_HEARTBEAT_KEY_PREFIX}{node_id}"
        await self._client.set(key, str(time.time()), ex=int(self._timeout_seconds))

    async def is_alive(self, node_id: str) -> bool:
        """Whether *node_id* has heartbeated within the timeout window."""
        key = f"{_HEARTBEAT_KEY_PREFIX}{node_id}"
        return bool(await self._client.exists(key))

    async def deregister(self, node_id: str) -> None:
        """Remove *node_id*'s heartbeat immediately (e.g. on graceful shutdown)."""
        await self._client.delete(f"{_HEARTBEAT_KEY_PREFIX}{node_id}")

    async def list_active_nodes(self) -> list[NodeHeartbeat]:
        """List every node currently believed alive ("Node Registration")."""
        nodes: list[NodeHeartbeat] = []
        async for key in self._client.scan_iter(match=f"{_HEARTBEAT_KEY_PREFIX}*"):
            key_text = key.decode("utf-8") if isinstance(key, bytes) else key
            value = await self._client.get(key_text)
            if value is None:
                continue
            value_text = value.decode("utf-8") if isinstance(value, bytes) else value
            node_id = key_text.removeprefix(_HEARTBEAT_KEY_PREFIX)
            nodes.append(NodeHeartbeat(node_id=node_id, last_seen=float(value_text)))
        return nodes


class HeartbeatSender:
    """Runs a background loop that periodically beats on behalf of one node."""

    def __init__(
        self,
        registry: HeartbeatRegistry,
        node_id: str,
        *,
        interval_seconds: float = DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
    ) -> None:
        self._registry = registry
        self._node_id = node_id
        self._interval_seconds = interval_seconds
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Send an immediate heartbeat and start the background refresh loop."""
        if self._task is not None:
            return
        await self._registry.beat(self._node_id)
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """Stop the background refresh loop and deregister immediately."""
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        await self._registry.deregister(self._node_id)

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self._interval_seconds)
            await self._registry.beat(self._node_id)


__all__ = ["HeartbeatRegistry", "HeartbeatSender", "NodeHeartbeat"]
