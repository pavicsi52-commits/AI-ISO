"""Connector SDK extension points.

Per docs/029_Enterprise_Plugin_Framework.md.txt "CONNECTOR EXTENSIONS":
allow plugins to register New Protocols, Cloud Providers, Industrial
Protocols, Storage Providers, Authentication Providers. A
:class:`~shared_core.plugins.extensions.NamespacedExtensions` scoped to
the ``"connector"`` namespace -- lets a plugin contribute a provider
implementation that a host service then registers into its own
:class:`shared_core.connectors.registry.ConnectorRegistry` (Prompt 027);
this module only tracks *what* a plugin contributed, not how the
Connector SDK itself connects/executes.
"""

from __future__ import annotations

from shared_core.plugins.extensions import ExtensionRegistry, NamespacedExtensions


class ConnectorExtensions(NamespacedExtensions):
    """Connector contribution categories: protocols, cloud providers,
    industrial protocols, storage providers, authentication providers.
    """

    def __init__(self, registry: ExtensionRegistry) -> None:
        super().__init__(registry, namespace="connector")


__all__ = ["ConnectorExtensions"]
