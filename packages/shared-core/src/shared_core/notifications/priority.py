"""Notification priority.

Per docs/025_Enterprise_Notification_Framework.md.txt "PRIORITY":
Critical, High, Normal, Low, Background. "Priority affects delivery
order." Reuses :class:`shared_core.enums.priority.Priority` directly
(the exact same five levels, already shared with
:mod:`shared_core.queue`) rather than defining a second, parallel
priority enum.
"""

from __future__ import annotations

from shared_core.enums.priority import Priority

_PRIORITY_RANK: dict[Priority, int] = {
    Priority.CRITICAL: 0,
    Priority.HIGH: 1,
    Priority.NORMAL: 2,
    Priority.LOW: 3,
    Priority.BACKGROUND: 4,
}


def priority_rank(priority: Priority) -> int:
    """Lower rank sorts first. Used to order a batch of notifications for delivery."""
    return _PRIORITY_RANK[priority]


def sort_by_priority(priorities: list[Priority]) -> list[Priority]:
    """Sort *priorities* into delivery order (most urgent first)."""
    return sorted(priorities, key=priority_rank)


__all__ = ["Priority", "priority_rank", "sort_by_priority"]
