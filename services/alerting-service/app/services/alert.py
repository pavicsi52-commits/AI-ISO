"""Alert lifecycle service -- this service's own central entity.

Owns every state transition an alert can undergo ("ALERT STATUS":
New, Open, Acknowledged, Investigating, Suppressed, Escalated,
Resolved, Closed, Expired), recording each into
:class:`~app.models.alert_history.AlertHistory` so a full audit trail
exists without any caller having to remember to write one.

**Transitions are validated, not free-form.** A resolved alert cannot
be silently re-acknowledged, and a closed alert is terminal. This is
enforced in :meth:`transition` via :data:`ALLOWED_TRANSITIONS` rather
than left to each caller's own discipline -- the same "the model
enforces its own invariants" posture every prior AI-IOS service's own
lifecycle entity established.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.enums.severity import Severity
from shared_core.exceptions.conflict import ConflictError

from app.models.alert_history import AlertHistory
from app.models.alert_instance import AlertInstance
from app.models.enums import AlertSource, AlertStatus
from app.repositories.alert_history import AlertHistoryRepository
from app.repositories.alert_instance import AlertInstanceRepository

ALLOWED_TRANSITIONS: dict[AlertStatus, frozenset[AlertStatus]] = {
    AlertStatus.NEW: frozenset(
        {
            AlertStatus.OPEN,
            AlertStatus.ACKNOWLEDGED,
            AlertStatus.SUPPRESSED,
            AlertStatus.ESCALATED,
            AlertStatus.RESOLVED,
            AlertStatus.EXPIRED,
        }
    ),
    AlertStatus.OPEN: frozenset(
        {
            AlertStatus.ACKNOWLEDGED,
            AlertStatus.INVESTIGATING,
            AlertStatus.SUPPRESSED,
            AlertStatus.ESCALATED,
            AlertStatus.RESOLVED,
            AlertStatus.EXPIRED,
        }
    ),
    AlertStatus.ACKNOWLEDGED: frozenset(
        {
            AlertStatus.INVESTIGATING,
            AlertStatus.ESCALATED,
            AlertStatus.RESOLVED,
            AlertStatus.SUPPRESSED,
        }
    ),
    AlertStatus.INVESTIGATING: frozenset(
        {AlertStatus.ESCALATED, AlertStatus.RESOLVED, AlertStatus.SUPPRESSED}
    ),
    AlertStatus.SUPPRESSED: frozenset(
        {AlertStatus.OPEN, AlertStatus.RESOLVED, AlertStatus.EXPIRED, AlertStatus.CLOSED}
    ),
    AlertStatus.ESCALATED: frozenset(
        {AlertStatus.ACKNOWLEDGED, AlertStatus.INVESTIGATING, AlertStatus.RESOLVED}
    ),
    AlertStatus.RESOLVED: frozenset({AlertStatus.CLOSED, AlertStatus.OPEN}),
    AlertStatus.EXPIRED: frozenset({AlertStatus.CLOSED}),
    AlertStatus.CLOSED: frozenset(),
}
"""Which statuses each status may move to.

``RESOLVED -> OPEN`` is deliberately allowed: a condition that recurs
after being resolved reopens the same alert rather than silently
dying. ``CLOSED`` is terminal -- reopening a closed alert would defeat
the point of closing it.
"""


class AlertService:
    """Owns the alert lifecycle and its own recorded history."""

    def __init__(self, alerts: AlertInstanceRepository, history: AlertHistoryRepository) -> None:
        self._alerts = alerts
        self._history = history

    async def get_by_id(self, alert_id: UUID) -> AlertInstance:
        """Return the alert identified by *alert_id*.

        Raises:
            NotFoundError: If no such alert exists.
        """
        return await self._alerts.require_by_id(alert_id)

    async def list_for_org(
        self,
        organization_id: UUID,
        *,
        status: AlertStatus | None = None,
        severity: Severity | None = None,
    ) -> list[AlertInstance]:
        """Every alert for *organization_id*, most recently triggered first."""
        return await self._alerts.list_for_org(organization_id, status=status, severity=severity)

    async def list_history(self, alert_id: UUID) -> list[AlertHistory]:
        """Every status transition recorded for *alert_id*."""
        return await self._history.list_for_alert(alert_id)

    async def create(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        rule_id: UUID | None,
        source: AlertSource,
        severity: Severity,
        title: str,
        message: str,
        fingerprint: str,
        source_reference: dict[str, Any],
        status: AlertStatus = AlertStatus.NEW,
        triggered_at: datetime | None = None,
    ) -> AlertInstance:
        """Raise a new alert, recording its own opening history entry."""
        moment = triggered_at or datetime.now(UTC)
        alert = await self._alerts.create(
            AlertInstance(
                organization_id=organization_id,
                project_id=project_id,
                rule_id=rule_id,
                source=source,
                severity=severity,
                status=status,
                title=title,
                message=message,
                fingerprint=fingerprint,
                source_reference=source_reference,
                triggered_at=moment,
            )
        )
        await self._record_history(
            alert, from_status=None, to_status=status, changed_by=None, reason=None, moment=moment
        )
        return alert

    async def update(
        self,
        alert_id: UUID,
        *,
        severity: Severity | None = None,
        title: str | None = None,
        message: str | None = None,
        assigned_to: UUID | None = None,
    ) -> AlertInstance:
        """Update an alert's own mutable fields ("Ownership"/"Assignment").

        Raises:
            NotFoundError: If no such alert exists.
        """
        alert = await self._alerts.require_by_id(alert_id)
        if severity is not None:
            alert.severity = severity
        if title is not None:
            alert.title = title
        if message is not None:
            alert.message = message
        if assigned_to is not None:
            alert.assigned_to = assigned_to
        return await self._alerts.update(alert)

    async def transition(
        self,
        alert_id: UUID,
        to_status: AlertStatus,
        *,
        changed_by: UUID | None = None,
        reason: str | None = None,
    ) -> AlertInstance:
        """Move an alert to *to_status*, recording the transition.

        Raises:
            NotFoundError: If no such alert exists.
            ConflictError: If the transition is not permitted from the
                alert's own current status.
        """
        alert = await self._alerts.require_by_id(alert_id)
        current = (
            alert.status if isinstance(alert.status, AlertStatus) else AlertStatus(alert.status)
        )
        if to_status not in ALLOWED_TRANSITIONS[current]:
            raise ConflictError(
                f"Alert {alert_id!r} cannot move from {str(current)!r} to {str(to_status)!r}."
            )

        moment = datetime.now(UTC)
        alert.status = to_status
        if to_status is AlertStatus.RESOLVED:
            alert.resolved_at = moment
        elif to_status is AlertStatus.CLOSED:
            alert.closed_at = moment
        elif to_status is AlertStatus.OPEN:
            # Reopening clears the prior resolution so elapsed-time
            # analytics measure the new occurrence, not the old one.
            alert.resolved_at = None
        alert = await self._alerts.update(alert)

        await self._record_history(
            alert,
            from_status=current,
            to_status=to_status,
            changed_by=changed_by,
            reason=reason,
            moment=moment,
        )
        return alert

    async def _record_history(
        self,
        alert: AlertInstance,
        *,
        from_status: AlertStatus | None,
        to_status: AlertStatus,
        changed_by: UUID | None,
        reason: str | None,
        moment: datetime,
    ) -> None:
        await self._history.create(
            AlertHistory(
                organization_id=alert.organization_id,
                project_id=alert.project_id,
                alert_id=alert.id,
                from_status=from_status,
                to_status=to_status,
                changed_by=changed_by,
                reason=reason,
                changed_at=moment,
            )
        )


__all__ = ["ALLOWED_TRANSITIONS", "AlertService"]
