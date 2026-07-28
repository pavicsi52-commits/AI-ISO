"""Escalation level resolution ("ESCALATION" "Support": Escalation
Policies, Time-based Escalation, Multi-level Escalation, Automatic
Escalation).

An :class:`~app.models.alert_escalation.AlertEscalationPolicy` stores
its own ordered ``levels`` inline as JSON (see that model's own
docstring for why). This module turns that raw JSON into a validated,
typed chain and decides which level is due for an alert that has gone
unacknowledged for a given elapsed time.

``delay_seconds`` on each level is measured from the alert's own
trigger time, cumulatively down the chain -- level 0 at its own delay,
level 1 at level 0's plus its own, and so on -- which is how a
multi-level policy ("page the on-call after 5 minutes, then their
manager 10 minutes after that") is naturally written.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from app.models.enums import EscalationTargetType


@dataclass(frozen=True, slots=True)
class EscalationLevel:
    """One validated level in an escalation policy's own chain."""

    sequence: int
    target_type: EscalationTargetType
    target_reference: str
    delay_seconds: float
    cumulative_delay_seconds: float


def parse_levels(raw_levels: Sequence[dict[str, Any]]) -> list[EscalationLevel]:
    """Turn a policy's own stored JSON levels into a validated chain.

    Malformed entries (missing/unknown ``target_type``, missing
    ``target_reference``, or a negative delay) are skipped rather than
    raising: one bad level in a stored policy must not make the whole
    policy un-runnable and silently stop every escalation it drives.
    """
    levels: list[EscalationLevel] = []
    cumulative = 0.0
    for sequence, raw in enumerate(raw_levels):
        target_reference = raw.get("target_reference")
        raw_target_type = raw.get("target_type")
        if not target_reference or raw_target_type is None:
            continue
        try:
            target_type = EscalationTargetType(str(raw_target_type))
        except ValueError:
            continue
        try:
            delay_seconds = float(raw.get("delay_seconds", 0.0))
        except (TypeError, ValueError):
            continue
        if delay_seconds < 0:
            continue
        cumulative += delay_seconds
        levels.append(
            EscalationLevel(
                sequence=sequence,
                target_type=target_type,
                target_reference=str(target_reference),
                delay_seconds=delay_seconds,
                cumulative_delay_seconds=cumulative,
            )
        )
    return levels


def due_level(levels: Sequence[EscalationLevel], elapsed_seconds: float) -> EscalationLevel | None:
    """Return the furthest level whose own cumulative delay has elapsed.

    Returns ``None`` if no level is due yet. Returning the *furthest*
    due level (rather than the first) means an escalation pass that ran
    late still lands on the correct level instead of replaying the
    whole chain from the beginning.
    """
    due = [level for level in levels if elapsed_seconds >= level.cumulative_delay_seconds]
    return due[-1] if due else None


__all__ = ["EscalationLevel", "due_level", "parse_levels"]
