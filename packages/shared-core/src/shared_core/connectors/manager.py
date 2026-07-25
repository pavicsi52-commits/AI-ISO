"""Connector manager.

Per docs/027_Enterprise_Connector_SDK.md.txt "ACCEPTANCE CRITERIA": the
top-level entry point tying registry, factory, and pooling together --
one :class:`ConnectorManager` per service, holding one
:class:`~shared_core.connectors.pool.ConnectorPool` per (provider,
target) pair it has been asked to reach, so repeated requests to the
same target reuse connections rather than reconnecting every time.
"""

from __future__ import annotations

from shared_core.connectors.base import BaseConnector
from shared_core.connectors.connection import ConnectionConfig
from shared_core.connectors.credentials import Credential
from shared_core.connectors.factory import build_connector_factory
from shared_core.connectors.pool import ConnectorPool
from shared_core.connectors.registry import ConnectorRegistry


class ConnectorManager:
    """Owns one connector registry and a pool per (provider, target) pair."""

    def __init__(self, registry: ConnectorRegistry | None = None) -> None:
        self.registry = registry if registry is not None else ConnectorRegistry()
        self._pools: dict[tuple[str, str], ConnectorPool] = {}

    def _pool_for(
        self, provider_name: str, config: ConnectionConfig, credential: Credential
    ) -> ConnectorPool:
        key = (provider_name, config.host)
        pool = self._pools.get(key)
        if pool is None:
            factory = build_connector_factory(self.registry, provider_name, config, credential)
            pool = ConnectorPool(factory)
            self._pools[key] = pool
        return pool

    async def get_connector(
        self, provider_name: str, config: ConnectionConfig, credential: Credential
    ) -> BaseConnector:
        """Acquire a pooled, connected connector for (*provider_name*, *config.host*)."""
        pool = self._pool_for(provider_name, config, credential)
        return await pool.acquire()

    async def release_connector(
        self, provider_name: str, config: ConnectionConfig, connector: BaseConnector
    ) -> None:
        """Return a connector acquired via :meth:`get_connector` back to its pool."""
        pool = self._pools.get((provider_name, config.host))
        if pool is not None:
            await pool.release(connector)

    def pool_count(self) -> int:
        """How many distinct (provider, target) pools this manager currently owns."""
        return len(self._pools)

    async def close(self) -> None:
        """Close every pool this manager owns ("Cleanup")."""
        for pool in self._pools.values():
            await pool.close()
        self._pools.clear()


__all__ = ["ConnectorManager"]
