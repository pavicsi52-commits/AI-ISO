"""Event versioning.

Per docs/020_Enterprise_Event_Framework.md.txt "EVENT VERSIONING": Every
event SHALL include version. Support v1/v2/v3. "Consumers must support
backward compatibility."
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from shared_core.events.exceptions import EventVersionMismatchError

_VERSION_PATTERN = re.compile(r"^v(\d+)$")

PayloadMigration = Callable[[dict[str, Any]], dict[str, Any]]


def parse_version(version: str) -> int:
    """Parse a ``"vN"`` version string into its integer ``N``.

    Raises:
        ValueError: If *version* doesn't match the ``vN`` format.
    """
    match = _VERSION_PATTERN.match(version)
    if not match:
        raise ValueError(f"Invalid event version format: {version!r}. Expected 'vN'.")
    return int(match.group(1))


def is_compatible(consumer_version: str, event_version: str) -> bool:
    """Return whether a consumer built for *consumer_version* can handle *event_version*.

    Backward compatibility only (docs/020): a v2-aware consumer can handle
    v1 and v2 events; a v1-only consumer cannot handle a v2 event (it may
    carry fields the consumer doesn't know about).
    """
    return parse_version(event_version) <= parse_version(consumer_version)


class VersionMigrator:
    """Registry of payload-upgrade functions, chaining v1->v2->v3.

    Lets a consumer that only understands the latest version still
    process an older event, by migrating its payload forward one version
    at a time before the consumer ever sees it.
    """

    def __init__(self) -> None:
        self._migrations: dict[tuple[str, int], PayloadMigration] = {}

    def register(self, event_name: str, from_version: str, migrate: PayloadMigration) -> None:
        """Register a function that upgrades *event_name*'s payload past *from_version*."""
        self._migrations[(event_name, parse_version(from_version))] = migrate

    def migrate(
        self, event_name: str, payload: dict[str, Any], *, from_version: str, to_version: str
    ) -> dict[str, Any]:
        """Migrate *payload* from *from_version* to *to_version*, applying every registered step.

        Raises:
            EventVersionMismatchError: If a required migration step isn't registered.
        """
        current = parse_version(from_version)
        target = parse_version(to_version)
        data = payload
        while current < target:
            step = self._migrations.get((event_name, current))
            if step is None:
                raise EventVersionMismatchError(
                    f"No migration registered for '{event_name}' from v{current} to v{current + 1}."
                )
            data = step(data)
            current += 1
        return data

    def has_migration_path(self, event_name: str, *, from_version: str, to_version: str) -> bool:
        """Return whether every migration step from *from_version* to *to_version* is registered."""
        current = parse_version(from_version)
        target = parse_version(to_version)
        while current < target:
            if (event_name, current) not in self._migrations:
                return False
            current += 1
        return True


__all__ = ["PayloadMigration", "VersionMigrator", "is_compatible", "parse_version"]
