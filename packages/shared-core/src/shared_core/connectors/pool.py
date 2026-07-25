"""Connection pooling.

Per docs/027_Enterprise_Connector_SDK.md.txt "CONNECTION MANAGEMENT":
Connection Pooling, Session Reuse. A generic, provider-agnostic pool of
already-constructed :class:`~shared_core.connectors.base.BaseConnector`
instances -- connecting/disconnecting is each connector's own concern;
this module only bounds how many are checked out concurrently and
reuses idle ones.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from shared_core.connectors.base import BaseConnector
from shared_core.connectors.constants import (
    DEFAULT_POOL_ACQUIRE_TIMEOUT_SECONDS,
    DEFAULT_POOL_MAX_SIZE,
)
from shared_core.connectors.exceptions import ConnectorTimeoutError

ConnectorFactory = Callable[[], Awaitable[BaseConnector]]


class ConnectorPool:
    """A bounded pool of connector instances, reused across callers ("Session Reuse")."""

    def __init__(
        self,
        factory: ConnectorFactory,
        *,
        max_size: int = DEFAULT_POOL_MAX_SIZE,
        acquire_timeout_seconds: float = DEFAULT_POOL_ACQUIRE_TIMEOUT_SECONDS,
    ) -> None:
        self._factory = factory
        self._max_size = max_size
        self._acquire_timeout_seconds = acquire_timeout_seconds
        self._idle: list[BaseConnector] = []
        self._size = 0
        self._condition = asyncio.Condition()

    @property
    def size(self) -> int:
        """How many connectors this pool currently owns (idle + checked out)."""
        return self._size

    async def acquire(self) -> BaseConnector:
        """Check out a connector, reusing an idle one or creating one up to ``max_size``.

        Raises:
            ConnectorTimeoutError: If no connector becomes available within
                ``acquire_timeout_seconds``.
        """
        try:
            return await asyncio.wait_for(self._acquire(), timeout=self._acquire_timeout_seconds)
        except TimeoutError as exc:
            raise ConnectorTimeoutError(
                f"Timed out acquiring a connector from the pool after "
                f"{self._acquire_timeout_seconds}s."
            ) from exc

    async def _acquire(self) -> BaseConnector:
        async with self._condition:
            while True:
                if self._idle:
                    return self._idle.pop()
                if self._size < self._max_size:
                    self._size += 1
                    break
                await self._condition.wait()
        try:
            return await self._factory()
        except Exception:
            async with self._condition:
                self._size -= 1
                self._condition.notify()
            raise

    async def release(self, connector: BaseConnector) -> None:
        """Return *connector* to the pool for reuse."""
        async with self._condition:
            self._idle.append(connector)
            self._condition.notify()

    async def discard(self, connector: BaseConnector) -> None:
        """Permanently remove *connector* from the pool (it failed and shouldn't be reused)."""
        async with self._condition:
            self._size -= 1
            self._condition.notify()
        await connector.disconnect()

    async def close(self) -> None:
        """Disconnect and discard every idle connector currently in the pool."""
        async with self._condition:
            idle, self._idle = self._idle, []
            self._size -= len(idle)
        for connector in idle:
            await connector.disconnect()

    @asynccontextmanager
    async def connector(self) -> AsyncIterator[BaseConnector]:
        """Acquire a connector for the duration of the context block, then release it."""
        instance = await self.acquire()
        try:
            yield instance
        finally:
            await self.release(instance)


__all__ = ["ConnectorFactory", "ConnectorPool"]
