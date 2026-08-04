"""Pure tests for app/priorities/engine.py -- no database, no fixtures."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.models.enums import JobPriority
from app.priorities.engine import QueueEntry, escalation_due, order_queue

_NOW = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)


class TestEscalationDue:
    def test_no_policy_never_escalates(self) -> None:
        assert (
            escalation_due(
                queued_at=_NOW - timedelta(hours=10),
                escalate_after_minutes=None,
                now=_NOW,
            )
            is False
        )

    def test_not_yet_due_before_the_threshold(self) -> None:
        assert (
            escalation_due(
                queued_at=_NOW - timedelta(minutes=10),
                escalate_after_minutes=30,
                now=_NOW,
            )
            is False
        )

    def test_due_once_the_threshold_has_elapsed(self) -> None:
        assert (
            escalation_due(
                queued_at=_NOW - timedelta(minutes=31),
                escalate_after_minutes=30,
                now=_NOW,
            )
            is True
        )

    def test_due_exactly_at_the_threshold(self) -> None:
        assert (
            escalation_due(
                queued_at=_NOW - timedelta(minutes=30),
                escalate_after_minutes=30,
                now=_NOW,
            )
            is True
        )


class TestOrderQueue:
    def test_critical_dispatches_before_low_regardless_of_queue_order(self) -> None:
        entries = [
            QueueEntry("low-1", JobPriority.LOW, _NOW - timedelta(minutes=5)),
            QueueEntry("critical-1", JobPriority.CRITICAL, _NOW),
        ]
        ordered = order_queue(entries)
        assert [entry.execution_id for entry in ordered] == ["critical-1", "low-1"]

    def test_same_priority_preserves_arrival_order(self) -> None:
        entries = [
            QueueEntry("second", JobPriority.NORMAL, _NOW),
            QueueEntry("first", JobPriority.NORMAL, _NOW - timedelta(minutes=1)),
        ]
        ordered = order_queue(entries)
        assert [entry.execution_id for entry in ordered] == ["first", "second"]

    def test_every_priority_band_sorts_correctly(self) -> None:
        entries = [
            QueueEntry("background", JobPriority.BACKGROUND, _NOW),
            QueueEntry("normal", JobPriority.NORMAL, _NOW),
            QueueEntry("critical", JobPriority.CRITICAL, _NOW),
            QueueEntry("high", JobPriority.HIGH, _NOW),
            QueueEntry("low", JobPriority.LOW, _NOW),
        ]
        ordered = order_queue(entries)
        assert [entry.execution_id for entry in ordered] == [
            "critical",
            "high",
            "normal",
            "low",
            "background",
        ]

    def test_empty_queue_orders_to_an_empty_list(self) -> None:
        assert order_queue([]) == []
