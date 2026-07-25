"""Event registry.

Central lookup of every registered event type, so publishers/consumers
can resolve an event name (and optionally a specific version) to its
:class:`~shared_core.events.base.BaseEvent` subclass. Per
docs/020_Enterprise_Event_Framework.md.txt "EVENT REGISTRY": Registration,
Lookup, Validation, Compatibility, Documentation.
"""

from __future__ import annotations

from typing import Any

from shared_core.events.base import BaseEvent
from shared_core.events.versioning import parse_version
from shared_core.exceptions.not_found import NotFoundError


class EventRegistry:
    """Maps event names (and, per name, every registered version) to their event class."""

    def __init__(self) -> None:
        self._events: dict[str, dict[str, type[BaseEvent]]] = {}

    def register(self, event_cls: type[BaseEvent]) -> type[BaseEvent]:
        """Register an event class under its name/version. Usable as a decorator."""
        self._events.setdefault(event_cls.event_name, {})[event_cls.event_version] = event_cls
        return event_cls

    def lookup(self, event_name: str, version: str | None = None) -> type[BaseEvent]:
        """Return the event class registered under ``event_name``.

        If *version* is omitted, returns the latest registered version.

        Raises:
            NotFoundError: If no event (or no matching version) is registered.
        """
        versions = self._events.get(event_name)
        if not versions:
            raise NotFoundError(f"No event registered under '{event_name}'.")
        if version is None:
            latest = max(versions, key=parse_version)
            return versions[latest]
        try:
            return versions[version]
        except KeyError as exc:
            raise NotFoundError(
                f"Event '{event_name}' has no registered version '{version}'."
            ) from exc

    def is_registered(self, event_name: str, version: str | None = None) -> bool:
        """Return whether ``event_name`` (and, if given, ``version``) is registered."""
        versions = self._events.get(event_name)
        if not versions:
            return False
        return version is None or version in versions

    def is_version_supported(self, event_name: str, version: str) -> bool:
        """Return whether ``version`` of ``event_name`` is registered ("Compatibility")."""
        return self.is_registered(event_name, version)

    def supported_versions(self, event_name: str) -> list[str]:
        """Return every registered version of ``event_name``, oldest first."""
        return sorted(self._events.get(event_name, {}), key=parse_version)

    def all_event_names(self) -> list[str]:
        """Return every registered event name."""
        return sorted(self._events)

    def describe(self, event_name: str, version: str | None = None) -> dict[str, Any]:
        """Return a JSON-schema description of an event, for self-service documentation."""
        event_cls = self.lookup(event_name, version)
        return event_cls.model_json_schema()


default_registry = EventRegistry()

__all__ = ["EventRegistry", "default_registry"]
