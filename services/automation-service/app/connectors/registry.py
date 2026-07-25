"""The process-wide :class:`~shared_core.connectors.registry
.ConnectorRegistry`, with every concrete provider this service ships
registered at import time -- see :mod:`app.connectors.ssh_connector`'s
own module docstring for why only ``ssh`` has a real provider class.
"""

from __future__ import annotations

from shared_core.connectors.registry import ConnectorRegistry

from app.connectors.ssh_connector import SshConnector


def build_connector_registry() -> ConnectorRegistry:
    """Build a fresh :class:`ConnectorRegistry` with every provider this
    service ships already registered.
    """
    registry = ConnectorRegistry()
    registry.register_decorated(SshConnector)
    return registry


__all__ = ["build_connector_registry"]
