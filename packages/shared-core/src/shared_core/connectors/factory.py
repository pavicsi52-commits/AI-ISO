"""Connector factory.

Per docs/027_Enterprise_Connector_SDK.md.txt "ACCEPTANCE CRITERIA":
Factory. Builds a connected
:class:`~shared_core.connectors.base.BaseConnector` instance from a
:class:`~shared_core.connectors.registry.ConnectorRegistry` lookup plus
a :class:`~shared_core.connectors.connection.ConnectionConfig`/
:class:`~shared_core.connectors.credentials.Credential` pair -- the one
place a caller turns "I want an SSH connector to this host" into a
live, ready-to-use connector instance, without importing a specific
provider module directly.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from shared_core.connectors.base import BaseConnector
from shared_core.connectors.connection import ConnectionConfig
from shared_core.connectors.credentials import Credential
from shared_core.connectors.registry import ConnectorRegistry


def create_connector(
    registry: ConnectorRegistry,
    provider_name: str,
    config: ConnectionConfig,
    credential: Credential,
) -> BaseConnector:
    """Instantiate (but do not yet connect) a registered provider's connector class.

    Raises:
        ProviderNotRegisteredError: If *provider_name* isn't registered.
    """
    connector_class = registry.get(provider_name)
    return connector_class(config, credential)


async def create_connected_connector(
    registry: ConnectorRegistry,
    provider_name: str,
    config: ConnectionConfig,
    credential: Credential,
) -> BaseConnector:
    """Instantiate a connector and connect it immediately."""
    instance = create_connector(registry, provider_name, config, credential)
    await instance.connect()
    return instance


def build_connector_factory(
    registry: ConnectorRegistry,
    provider_name: str,
    config: ConnectionConfig,
    credential: Credential,
) -> Callable[[], Awaitable[BaseConnector]]:
    """Build a zero-arg async factory usable directly with
    :class:`~shared_core.connectors.pool.ConnectorPool` ("Factory").
    """

    async def factory() -> BaseConnector:
        return await create_connected_connector(registry, provider_name, config, credential)

    return factory


__all__ = ["build_connector_factory", "create_connected_connector", "create_connector"]
