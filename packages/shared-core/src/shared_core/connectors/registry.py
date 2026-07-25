"""Connector registry.

Per docs/027_Enterprise_Connector_SDK.md.txt "ACCEPTANCE CRITERIA":
Registry. The in-process, authoritative map of provider name ->
connector class. Providers (built in a later phase; see README
"Provider Packages") register themselves here -- via :meth:`register`
directly, or by decorating their class with ``@connector(provider_name)``
(see :mod:`~shared_core.connectors.decorators`) and passing it to
:meth:`register_decorated` -- so :mod:`~shared_core.connectors.factory`
can look one up by name without hard-importing every provider module.
"""

from __future__ import annotations

from shared_core.connectors.decorators import ConnectorClass, get_provider_name
from shared_core.connectors.exceptions import ProviderNotRegisteredError


class ConnectorRegistry:
    """The authoritative in-process map of provider name -> connector class."""

    def __init__(self) -> None:
        self._classes: dict[str, ConnectorClass] = {}

    def register(self, provider_name: str, connector_class: ConnectorClass) -> None:
        """Register *connector_class* under *provider_name* ("Register")."""
        self._classes[provider_name] = connector_class

    def register_decorated(self, connector_class: ConnectorClass) -> None:
        """Register a class already decorated with ``@connector(provider_name)``.

        Raises:
            ValueError: If *connector_class* wasn't decorated.
        """
        provider_name = get_provider_name(connector_class)
        if provider_name is None:
            raise ValueError(f"{connector_class.__name__} was not decorated with @connector(...).")
        self.register(provider_name, connector_class)

    def unregister(self, provider_name: str) -> None:
        """Remove a provider's registration. A no-op if it isn't registered."""
        self._classes.pop(provider_name, None)

    def get(self, provider_name: str) -> ConnectorClass:
        """Look up a provider's connector class by name.

        Raises:
            ProviderNotRegisteredError: If no class is registered under *provider_name*.
        """
        try:
            return self._classes[provider_name]
        except KeyError as exc:
            raise ProviderNotRegisteredError(
                f"No connector is registered for provider {provider_name!r}."
            ) from exc

    def is_registered(self, provider_name: str) -> bool:
        """Whether a connector class is registered under *provider_name*."""
        return provider_name in self._classes

    def list_providers(self) -> list[str]:
        """Every currently registered provider name."""
        return list(self._classes)


__all__ = ["ConnectorRegistry"]
