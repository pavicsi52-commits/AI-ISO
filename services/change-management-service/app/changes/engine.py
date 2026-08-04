"""The change lifecycle: legal transitions, CAB eligibility, durations.

Pure -- no database, no clock it was not handed. ``app/services/change.py``
supplies the database and the clock around these decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from shared_core.exceptions.validation import ValidationError

from app.models.enums import HIGH_RISK_LEVELS, ChangeStatus, ChangeType, RiskLevel

ALLOWED_TRANSITIONS: dict[ChangeStatus, frozenset[ChangeStatus]] = {
    ChangeStatus.DRAFT: frozenset({ChangeStatus.SUBMITTED, ChangeStatus.CANCELLED}),
    ChangeStatus.SUBMITTED: frozenset(
        {ChangeStatus.RISK_ASSESSMENT, ChangeStatus.DRAFT, ChangeStatus.CANCELLED}
    ),
    ChangeStatus.RISK_ASSESSMENT: frozenset(
        {ChangeStatus.PENDING_APPROVAL, ChangeStatus.CANCELLED}
    ),
    ChangeStatus.PENDING_APPROVAL: frozenset(
        {
            ChangeStatus.CAB_REVIEW,
            ChangeStatus.SCHEDULED,
            ChangeStatus.REJECTED,
            ChangeStatus.CANCELLED,
        }
    ),
    ChangeStatus.CAB_REVIEW: frozenset(
        {ChangeStatus.SCHEDULED, ChangeStatus.REJECTED, ChangeStatus.CANCELLED}
    ),
    ChangeStatus.SCHEDULED: frozenset({ChangeStatus.READY, ChangeStatus.CANCELLED}),
    ChangeStatus.READY: frozenset({ChangeStatus.IN_PROGRESS, ChangeStatus.CANCELLED}),
    ChangeStatus.IN_PROGRESS: frozenset({ChangeStatus.VALIDATION, ChangeStatus.ROLLED_BACK}),
    ChangeStatus.VALIDATION: frozenset({ChangeStatus.COMPLETED, ChangeStatus.ROLLED_BACK}),
    ChangeStatus.COMPLETED: frozenset({ChangeStatus.CLOSED}),
    ChangeStatus.ROLLED_BACK: frozenset({ChangeStatus.CLOSED}),
    ChangeStatus.CANCELLED: frozenset(),
    ChangeStatus.REJECTED: frozenset(),
    ChangeStatus.CLOSED: frozenset(),
}
"""Which lifecycle moves are legal.

**``CANCELLED``, ``REJECTED``, and ``CLOSED`` are true dead ends** -- the
same reasoning Prompt 050's policy lifecycle and Prompt 052's postmortem
lifecycle both apply: a formal decision that people already acted on
does not get silently reopened. A change that needs to try again is a
new change, optionally linked to the old one by a
:class:`~app.models.enums.RelationshipKind.RELATED_TO` relationship --
not a reason to widen this table.
"""


def validate_transition(current: ChangeStatus, target: ChangeStatus) -> None:
    """Confirm *target* is reachable from *current*.

    Raises:
        ValidationError: If it is not.
    """
    if target not in ALLOWED_TRANSITIONS[current]:
        allowed = ", ".join(sorted(str(one) for one in ALLOWED_TRANSITIONS[current])) or "nothing"
        raise ValidationError(
            f"A change that is {current!s} cannot move to {target!s}. Allowed from here: {allowed}."
        )


def is_emergency(change_type: ChangeType) -> bool:
    """Whether a change type may implement before its approval completes."""
    return change_type is ChangeType.EMERGENCY


def requires_cab_review(
    *, risk_level: RiskLevel | None, change_type: ChangeType, standard_change_requires_cab: bool
) -> bool:
    """Whether a change must pass a Change Advisory Board review.

    A standard change is pre-approved and repeatable by definition, so
    it never needs its own board review unless an organization has
    explicitly opted its standard-change templates back in (a real, if
    unusual, policy some regulated environments require). An emergency
    change is never gated on CAB at all -- see
    ``ChangeManagementServiceSettings.emergency_change_requires_post_hoc_approval``
    -- because CAB review, if it happens for one, happens after
    implementation, not before.

    Every other type routes through CAB once its assessed risk reaches
    :data:`~app.models.enums.HIGH_RISK_LEVELS`. An unassessed change
    (``risk_level is None``) is treated as requiring CAB: the absence of
    an assessment is not evidence of low risk, and defaulting the other
    way would let a change skip a board review simply by skipping its
    risk assessment first.
    """
    if change_type is ChangeType.STANDARD:
        return standard_change_requires_cab
    if change_type is ChangeType.EMERGENCY:
        return False
    return risk_level is None or risk_level in HIGH_RISK_LEVELS


@dataclass(frozen=True, slots=True)
class ChangeDurations:
    """How long a change spent in each timed phase, in seconds."""

    approval_duration_seconds: float | None
    implementation_duration_seconds: float | None


def compute_durations(
    *,
    submitted_at: datetime | None,
    approved_at: datetime | None,
    actual_start_at: datetime | None,
    actual_end_at: datetime | None,
) -> ChangeDurations:
    """Derive the two duration metrics analytics and reporting both read.

    Each is ``None`` until both of its own endpoints are known, rather
    than a guess from whichever timestamp happens to exist -- a change
    still awaiting approval has no approval duration yet, not a zero one.
    """
    approval = (
        (approved_at - submitted_at).total_seconds()
        if submitted_at is not None and approved_at is not None
        else None
    )
    implementation = (
        (actual_end_at - actual_start_at).total_seconds()
        if actual_start_at is not None and actual_end_at is not None
        else None
    )
    return ChangeDurations(
        approval_duration_seconds=approval, implementation_duration_seconds=implementation
    )


__all__ = [
    "ALLOWED_TRANSITIONS",
    "ChangeDurations",
    "compute_durations",
    "is_emergency",
    "requires_cab_review",
    "validate_transition",
]
