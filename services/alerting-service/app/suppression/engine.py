"""Suppression decision engine ("SUPPRESSION" "Support").

Decides whether an alert about to be raised should instead be recorded
as ``SUPPRESSED``. Pure decision logic over already-fetched rows -- the
database reads belong to the calling service, so this module stays
synchronous, side-effect-free, and directly unit-testable.

Matching is by ``scope_reference``: a suppression with none set is
organization-wide; one with a value suppresses only alerts whose own
``source_reference`` contains that value under any identity key (e.g.
suppressing ``"target_id"`` ``"abc"`` silences every alert about that
target). This is the same "identify by string, not a typed foreign key
into every possible target" shape
:class:`~app.models.alert_suppression.AlertSuppression` itself
documents.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.models.alert_maintenance_window import AlertMaintenanceWindow
from app.models.alert_suppression import AlertSuppression
from app.models.enums import SuppressionType
from app.suppression.maintenance import is_window_active


@dataclass(frozen=True, slots=True)
class SuppressionDecision:
    """Why (or whether) an alert is suppressed."""

    suppressed: bool
    suppression_type: SuppressionType | None = None
    reason: str | None = None


NOT_SUPPRESSED = SuppressionDecision(suppressed=False)


def _matches_scope(scope_reference: str | None, source_reference: dict[str, Any]) -> bool:
    if scope_reference is None:
        return True
    return any(str(value) == scope_reference for value in source_reference.values())


def evaluate_suppression(
    *,
    source_reference: dict[str, Any],
    suppressions: Sequence[AlertSuppression],
    maintenance_windows: Sequence[AlertMaintenanceWindow],
    moment: datetime,
) -> SuppressionDecision:
    """Decide whether an alert should be suppressed at *moment*.

    Maintenance windows are checked first: an in-force window is the
    most explicit, operator-declared reason to stay silent, and
    reporting it as the cause is more useful to an on-call engineer
    than a generic rule-based suppression that happens to also match.
    """
    for window in maintenance_windows:
        if is_window_active(window, moment) and _matches_scope(
            window.scope_reference, source_reference
        ):
            return SuppressionDecision(
                suppressed=True,
                suppression_type=SuppressionType.MAINTENANCE_WINDOW,
                reason=f"Maintenance window {window.name!r} is in force.",
            )

    for suppression in suppressions:
        if _matches_scope(suppression.scope_reference, source_reference):
            return SuppressionDecision(
                suppressed=True,
                suppression_type=suppression.suppression_type,
                reason=suppression.reason
                or f"Suppression {suppression.suppression_type!s} is in force.",
            )

    return NOT_SUPPRESSED


__all__ = ["NOT_SUPPRESSED", "SuppressionDecision", "evaluate_suppression"]
