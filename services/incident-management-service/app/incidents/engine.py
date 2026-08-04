"""Incident identity, lifecycle, and the MTTA/MTTR arithmetic.

Pure: fingerprinting, status transitions, and duration metrics all take
their inputs as arguments and return a value. What lives here decides
whether a new alert firing opens a new incident or joins an existing
one, and whether a requested status change is one this incident's
current status actually allows -- two decisions expensive enough to get
wrong that they deserve to be tested without a database in the loop.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime

from shared_core.exceptions.validation import ValidationError

from app.models.enums import TERMINAL_INCIDENT_STATUSES, IncidentStatus

CORRELATION_WINDOW_DEFAULT_MINUTES = 15
"""How long a fingerprint stays open for a new firing to join, absent an
explicit window. See :func:`correlates` for why this is bounded rather
than "forever"."""

MAX_PERCENTILE = 100.0
"""A percentile is a point on a 0-100 scale; nothing above it is meaningful."""


def fingerprint(*, source: str, category: str, key: str) -> str:
    """A stable identity for "this same underlying condition".

    *key* is the caller's own notion of what makes two firings the same
    thing -- a monitoring target id, an alert rule id, a validation
    check id. This function does not guess at that; it only hashes what
    it is given, so a caller that wants coarser or finer correlation
    controls it entirely by what it passes as *key*.
    """
    return hashlib.sha256(f"{source}|{category}|{key}".encode()).hexdigest()[:32]


def correlates(
    *,
    existing_fingerprint: str,
    new_fingerprint: str,
    existing_status: IncidentStatus,
    existing_last_activity: datetime,
    now: datetime,
    window_minutes: int = CORRELATION_WINDOW_DEFAULT_MINUTES,
) -> bool:
    """Whether a new firing should join an existing open incident.

    **Three conditions, all required.** The fingerprints must match --
    obviously. The existing incident must still be open: a firing that
    recurs after the incident closed is a new occurrence of an old
    problem, not a continuation of the resolved one, and correlating it
    onto the closed row would silently reopen history a closure was
    meant to finalise. And the correlation window must not have lapsed:
    without a window, an alert that fires monthly against a fingerprint
    from a year-old incident would join that ancient row forever, which
    makes "when did this actually start recurring" unanswerable.
    """
    if existing_fingerprint != new_fingerprint:
        return False
    if existing_status in TERMINAL_INCIDENT_STATUSES or existing_status == IncidentStatus.RESOLVED:
        return False
    elapsed_minutes = (now - existing_last_activity).total_seconds() / 60.0
    return elapsed_minutes <= window_minutes


# ---- lifecycle -----------------------------------------------------------

ALLOWED_TRANSITIONS: dict[IncidentStatus, frozenset[IncidentStatus]] = {
    IncidentStatus.NEW: frozenset(
        {IncidentStatus.ASSIGNED, IncidentStatus.ACKNOWLEDGED, IncidentStatus.CANCELLED}
    ),
    IncidentStatus.ASSIGNED: frozenset(
        {IncidentStatus.ACKNOWLEDGED, IncidentStatus.INVESTIGATING, IncidentStatus.CANCELLED}
    ),
    IncidentStatus.ACKNOWLEDGED: frozenset(
        {IncidentStatus.INVESTIGATING, IncidentStatus.MITIGATING, IncidentStatus.CANCELLED}
    ),
    IncidentStatus.INVESTIGATING: frozenset(
        {
            IncidentStatus.MITIGATING,
            IncidentStatus.MONITORING,
            IncidentStatus.RESOLVED,
            IncidentStatus.CANCELLED,
        }
    ),
    IncidentStatus.MITIGATING: frozenset(
        {IncidentStatus.MONITORING, IncidentStatus.RESOLVED, IncidentStatus.INVESTIGATING}
    ),
    IncidentStatus.MONITORING: frozenset({IncidentStatus.RESOLVED, IncidentStatus.INVESTIGATING}),
    IncidentStatus.RESOLVED: frozenset({IncidentStatus.CLOSED, IncidentStatus.INVESTIGATING}),
    IncidentStatus.CLOSED: frozenset({IncidentStatus.INVESTIGATING}),
    IncidentStatus.CANCELLED: frozenset(),
    IncidentStatus.MERGED: frozenset(),
}
"""Which lifecycle moves are legal.

**``RESOLVED`` and ``CLOSED`` may both move back to ``INVESTIGATING``.**
That is a reopen, not an error -- the single most operationally
important edge this table has, because "the fix did not actually hold"
is a real outcome and an incident management tool that cannot represent
it will simply get a second incident opened for the same problem
instead, which is worse for every trend number this service reports.
``CANCELLED`` and ``MERGED`` are the only true dead ends: a cancelled
incident was never real, and a merged one's own row is no longer where
work happens.
"""


def validate_transition(current: IncidentStatus, target: IncidentStatus) -> None:
    """Refuse a status change this incident's lifecycle does not allow.

    Raises:
        ValidationError: If *target* is not reachable from *current*.
    """
    if target not in ALLOWED_TRANSITIONS[current]:
        allowed = ", ".join(sorted(str(one) for one in ALLOWED_TRANSITIONS[current])) or "nothing"
        raise ValidationError(
            f"An incident that is {str(current)!r} cannot move to {str(target)!r}. "
            f"Allowed from here: {allowed}."
        )


def is_reopen(current: IncidentStatus, target: IncidentStatus) -> bool:
    """Whether this transition is a reopen rather than forward progress."""
    return current in (IncidentStatus.RESOLVED, IncidentStatus.CLOSED) and target not in (
        IncidentStatus.RESOLVED,
        IncidentStatus.CLOSED,
    )


# ---- duration metrics ------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DurationMetrics:
    """The two headline numbers a review asks for, in seconds."""

    mtta_seconds: float | None
    mttr_seconds: float | None


def compute_durations(
    *, detected_at: datetime, acknowledged_at: datetime | None, resolved_at: datetime | None
) -> DurationMetrics:
    """MTTA and MTTR for one incident.

    Both are ``None`` until the corresponding moment is recorded --
    never zero. A zero MTTR on an incident that has not resolved yet
    would read as "resolved instantly," which is the opposite of what
    "not yet known" means, and an average over a mix of the two would be
    silently wrong in the optimistic direction.
    """
    mtta = (acknowledged_at - detected_at).total_seconds() if acknowledged_at is not None else None
    mttr = (resolved_at - detected_at).total_seconds() if resolved_at is not None else None
    return DurationMetrics(mtta_seconds=mtta, mttr_seconds=mttr)


def percentile(values: list[float], *, pct: float) -> float | None:
    """The *pct*-th percentile of *values*, nearest-rank, or ``None`` if empty.

    Nearest-rank rather than interpolated, deliberately: an interpolated
    p90 MTTR of "4h 23m" implies precision the underlying handful of
    incidents in most organizations' windows does not support, and
    nearest-rank always names an incident that actually happened at that
    duration rather than a number between two of them.
    """
    if not values:
        return None
    if not 0 < pct <= MAX_PERCENTILE:
        raise ValueError(f"pct must be in (0, {MAX_PERCENTILE}], got {pct!r}.")
    ordered = sorted(values)
    index = max(0, int((pct / 100.0) * len(ordered)) - 1)
    return ordered[min(index, len(ordered) - 1)]


__all__ = [
    "ALLOWED_TRANSITIONS",
    "CORRELATION_WINDOW_DEFAULT_MINUTES",
    "DurationMetrics",
    "compute_durations",
    "correlates",
    "fingerprint",
    "is_reopen",
    "percentile",
    "validate_transition",
]
