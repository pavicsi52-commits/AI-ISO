"""Extension points.

Per docs/029_Enterprise_Plugin_Framework.md.txt "EXTENSION POINTS": REST
API, Backend Services, Workflow SDK, Connector SDK, Notification
Framework, Scheduler Framework, Monitoring Framework, Telemetry
Framework, Validation Framework, AI Framework, Dashboard UI, CLI. A
generic, named registry any part of the platform can expose as a place
plugins contribute into -- the domain-specific registries in
:mod:`shared_core.plugins.ui`/:mod:`shared_core.plugins.backend`/
:mod:`shared_core.plugins.workflow`/:mod:`shared_core.plugins.connector`/
:mod:`shared_core.plugins.ai` are each one namespaced view over this
same mechanism, not a separate implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from shared_core.plugins.exceptions import ExtensionPointNotFoundError


@dataclass(frozen=True, slots=True)
class ExtensionContribution:
    """One plugin's contribution to an extension point."""

    plugin_id: str
    name: str
    value: Any


class ExtensionPoint:
    """A single named place plugins can contribute into."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._contributions: dict[str, ExtensionContribution] = {}

    def contribute(self, plugin_id: str, name: str, value: Any) -> None:
        """Register *value* under *name*, attributed to *plugin_id*."""
        self._contributions[name] = ExtensionContribution(
            plugin_id=plugin_id, name=name, value=value
        )

    def withdraw(self, name: str) -> None:
        """Remove a contribution. A no-op if it isn't registered."""
        self._contributions.pop(name, None)

    def withdraw_all_from(self, plugin_id: str) -> None:
        """Remove every contribution *plugin_id* made ("Uninstall" cleanup)."""
        for name in [n for n, c in self._contributions.items() if c.plugin_id == plugin_id]:
            self._contributions.pop(name, None)

    def get(self, name: str) -> Any:
        """Look up one contribution's value by *name*.

        Raises:
            ExtensionPointNotFoundError: If *name* isn't registered here.
        """
        try:
            return self._contributions[name].value
        except KeyError as exc:
            raise ExtensionPointNotFoundError(
                f"No contribution named {name!r} registered at extension point {self.name!r}."
            ) from exc

    def list_contributions(self) -> list[ExtensionContribution]:
        """Every contribution currently registered here."""
        return list(self._contributions.values())


class ExtensionRegistry:
    """Owns every named :class:`ExtensionPoint` a service exposes."""

    def __init__(self) -> None:
        self._points: dict[str, ExtensionPoint] = {}

    def point(self, name: str) -> ExtensionPoint:
        """Get (creating on first use) the named extension point."""
        return self._points.setdefault(name, ExtensionPoint(name))

    def list_points(self) -> list[str]:
        """Every extension point name that has been touched so far."""
        return list(self._points)

    def withdraw_all_from(self, plugin_id: str) -> None:
        """Remove every contribution *plugin_id* made, across every extension point."""
        for extension_point in self._points.values():
            extension_point.withdraw_all_from(plugin_id)


class NamespacedExtensions:
    """A thin, prefix-scoped view over an :class:`ExtensionRegistry`.

    Each of :mod:`~shared_core.plugins.ui`/:mod:`~shared_core.plugins.backend`/
    :mod:`~shared_core.plugins.workflow`/:mod:`~shared_core.plugins.connector`/
    :mod:`~shared_core.plugins.ai` subclasses this with its own fixed
    ``namespace`` rather than reimplementing the same three methods.
    """

    def __init__(self, registry: ExtensionRegistry, *, namespace: str) -> None:
        self._registry = registry
        self._namespace = namespace

    def register(self, category: str, plugin_id: str, name: str, value: Any) -> None:
        """Contribute *value* under *name* to *category* within this namespace."""
        self._registry.point(f"{self._namespace}.{category}").contribute(plugin_id, name, value)

    def get(self, category: str, name: str) -> Any:
        """Look up one contribution to *category* by *name*.

        Raises:
            ExtensionPointNotFoundError: If *name* isn't registered under *category*.
        """
        return self._registry.point(f"{self._namespace}.{category}").get(name)

    def list_contributions(self, category: str) -> list[ExtensionContribution]:
        """Every contribution currently registered to *category*."""
        return self._registry.point(f"{self._namespace}.{category}").list_contributions()

    def withdraw_all_from(self, plugin_id: str) -> None:
        """Remove every contribution *plugin_id* made within this namespace."""
        for point_name in self._registry.list_points():
            if point_name.startswith(f"{self._namespace}."):
                self._registry.point(point_name).withdraw_all_from(plugin_id)


__all__ = ["ExtensionContribution", "ExtensionPoint", "ExtensionRegistry", "NamespacedExtensions"]
