"""Detecting scheduling conflicts between two changes.

Pure -- takes two changes' windows and the resources each touches,
returns which kinds of conflict, if any, exist between them.
``app/services/conflict.py`` supplies the database and iterates every
pair worth comparing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.models.enums import ConflictKind


@dataclass(frozen=True, slots=True)
class ChangeWindow:
    """One change's schedule and footprint, as the conflict engine needs it."""

    starts_at: datetime
    ends_at: datetime
    assets: frozenset[str] = field(default_factory=frozenset)
    services: frozenset[str] = field(default_factory=frozenset)
    applications: frozenset[str] = field(default_factory=frozenset)
    dependencies: frozenset[str] = field(default_factory=frozenset)


def windows_overlap(a: ChangeWindow, b: ChangeWindow, *, slack: timedelta) -> bool:
    """Whether two windows overlap once *slack* pads the first one on both sides.

    Two changes scheduled back-to-back on the same asset are a real
    scheduling risk even when their windows never technically touch --
    the crew finishing the first one is the crew about to start the
    second. Padding only one side of the comparison would make the
    function order-dependent for what is actually a symmetric question,
    so *a* is padded and compared against *b*'s own untouched bounds;
    callers that care about the relationship both ways call this with
    the pair swapped, which is exactly as cheap and never ambiguous.
    """
    padded_start = a.starts_at - slack
    padded_end = a.ends_at + slack
    return padded_start < b.ends_at and b.starts_at < padded_end


def detect_conflicts(a: ChangeWindow, b: ChangeWindow, *, slack: timedelta) -> list[ConflictKind]:
    """Every conflict kind that applies between two changes.

    Empty when the windows do not overlap at all, even with slack
    applied -- shared resources on two changes scheduled months apart
    are not a scheduling conflict, they are just two changes that will
    eventually both touch the same thing.
    """
    if not (windows_overlap(a, b, slack=slack) or windows_overlap(b, a, slack=slack)):
        return []

    kinds = [ConflictKind.SCHEDULE]
    if a.assets & b.assets:
        kinds.append(ConflictKind.ASSET)
    if a.services & b.services:
        kinds.append(ConflictKind.SERVICE)
    if a.applications & b.applications:
        kinds.append(ConflictKind.APPLICATION)
    if a.dependencies & b.dependencies:
        kinds.append(ConflictKind.DEPENDENCY)
    return kinds


__all__ = ["ChangeWindow", "detect_conflicts", "windows_overlap"]
