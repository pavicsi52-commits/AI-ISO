"""Plugin versioning.

Per docs/029_Enterprise_Plugin_Framework.md.txt "VERSIONING": Semantic
Versioning, Compatibility Checks, Upgrade Paths, Downgrade Support,
Migration Hooks. Wraps ``packaging.version.Version``/
``packaging.specifiers.SpecifierSet`` -- the standard, PEP 440/semver-
aware library already present transitively in this monorepo's own
tooling -- rather than hand-rolling version-string comparison.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from shared_core.plugins.exceptions import VersionIncompatibleError

MigrationHook = Callable[[str, str], Awaitable[None]]


def parse_version(text: str) -> Version:
    """Parse a semantic version string.

    Raises:
        VersionIncompatibleError: If *text* isn't a valid version.
    """
    try:
        return Version(text)
    except InvalidVersion as exc:
        raise VersionIncompatibleError(f"{text!r} is not a valid plugin version.") from exc


def is_compatible(version: str, constraint: str) -> bool:
    """Whether *version* satisfies *constraint* (e.g. ``">=1.0.0,<2.0.0"``, ``"*"``)."""
    if constraint in ("", "*"):
        return True
    try:
        specifier = SpecifierSet(constraint)
    except InvalidSpecifier as exc:
        raise VersionIncompatibleError(
            f"{constraint!r} is not a valid version constraint."
        ) from exc
    return parse_version(version) in specifier


def require_compatible(version: str, constraint: str, *, subject: str) -> None:
    """Raise unless *version* satisfies *constraint*.

    Raises:
        VersionIncompatibleError: If *version* does not satisfy *constraint*.
    """
    if not is_compatible(version, constraint):
        raise VersionIncompatibleError(
            f"{subject} version {version!r} does not satisfy constraint {constraint!r}."
        )


def is_upgrade(from_version: str, to_version: str) -> bool:
    """Whether *to_version* is strictly newer than *from_version* ("Upgrade Paths")."""
    return parse_version(to_version) > parse_version(from_version)


def is_downgrade(from_version: str, to_version: str) -> bool:
    """Whether *to_version* is strictly older than *from_version* ("Downgrade Support")."""
    return parse_version(to_version) < parse_version(from_version)


class MigrationRegistry:
    """Registers migration hooks run when a plugin's data/config moves between versions."""

    def __init__(self) -> None:
        self._hooks: dict[tuple[str, str], MigrationHook] = {}

    def register(self, from_version: str, to_version: str, hook: MigrationHook) -> None:
        """Register *hook* to run for exactly (*from_version* -> *to_version*)."""
        self._hooks[(from_version, to_version)] = hook

    def get(self, from_version: str, to_version: str) -> MigrationHook | None:
        """Return the registered hook for this exact version transition, if any."""
        return self._hooks.get((from_version, to_version))

    async def migrate(self, from_version: str, to_version: str) -> bool:
        """Run the registered migration hook for this transition, if any.

        Returns whether a hook was found and run.
        """
        hook = self.get(from_version, to_version)
        if hook is None:
            return False
        await hook(from_version, to_version)
        return True


__all__ = [
    "MigrationHook",
    "MigrationRegistry",
    "is_compatible",
    "is_downgrade",
    "is_upgrade",
    "parse_version",
    "require_compatible",
]
