"""Priority escalation and queue ordering.

Pure -- no database, no clock it was not handed.
``app/services/priority.py`` supplies the database and the "now" around
these decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.models.enums import PRIORITY_ORDER, JobPriority


def escalation_due(
    *, queued_at: datetime, escalate_after_minutes: int | None, now: datetime
) -> bool:
    """Whether a job that has been queued since *queued_at* is overdue for escalation.

    ``escalate_after_minutes is None`` means this priority band has no
    configured escalation policy -- it never escalates, rather than
    escalating on some made-up default. A policy an organization never
    configured is not evidence they want the platform default; see
    ``app/services/priority.py``'s own notes on why an absent policy row
    is silence, not a zero.
    """
    if escalate_after_minutes is None:
        return False
    elapsed_minutes = (now - queued_at).total_seconds() / 60
    return elapsed_minutes >= escalate_after_minutes


@dataclass(frozen=True, slots=True)
class QueueEntry:
    """One queued execution, as the ordering function needs it."""

    execution_id: str
    priority: JobPriority
    queued_at: datetime


def order_queue(entries: list[QueueEntry]) -> list[QueueEntry]:
    """Order queued executions for dispatch: most urgent priority first, FIFO within a band.

    Priority is the primary sort key precisely so a flood of ``LOW``
    work queued a moment earlier never delays a ``CRITICAL`` job queued
    a moment later -- but within one band, arrival order is preserved,
    so two jobs at the same priority never race for dispatch order on
    anything other than when they were actually queued.
    """
    return sorted(entries, key=lambda entry: (PRIORITY_ORDER[entry.priority], entry.queued_at))


__all__ = ["QueueEntry", "escalation_due", "order_queue"]
