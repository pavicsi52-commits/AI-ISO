"""Optimistic locking / versioning.

Per docs/018_Enterprise_Database_Framework.md.txt "VERSIONING": Optimistic
Locking, Version Increment, Conflict Detection, Concurrent Update
Protection. Every entity carries the ``version`` column from
:class:`shared_core.base.VersionMixin`; this module is the single place
that checks and increments it, so :mod:`shared_core.database.repository`
and any custom update path use the same conflict semantics.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from shared_core.database.exceptions import VersionConflictError


@runtime_checkable
class Versioned(Protocol):
    """Structural type for any entity carrying a ``version`` column."""

    version: int


def check_version(entity: Versioned, expected_version: int) -> None:
    """Raise :class:`VersionConflictError` if *entity*'s version has moved on.

    Call before mutating *entity* when the caller read it earlier and wants
    to guarantee no concurrent update happened in between.
    """
    if entity.version != expected_version:
        raise VersionConflictError(
            f"{type(entity).__name__} was modified by another request. "
            f"Expected version {expected_version}, found {entity.version}."
        )


def increment_version(entity: Versioned) -> int:
    """Increment *entity*'s version and return the new value.

    Call exactly once per successful update -- calling it more than once for
    the same logical change would let a single writer's update look like
    multiple concurrent ones to the next reader.
    """
    entity.version += 1
    return entity.version


__all__ = ["Versioned", "check_version", "increment_version"]
