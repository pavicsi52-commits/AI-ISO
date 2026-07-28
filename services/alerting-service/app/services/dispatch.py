"""Notification dispatch and escalation advancement.

Two related jobs the escalation worker drives on a schedule:

- :meth:`dispatch_alert` fans a newly raised alert out to every route
  its own severity matches ("ROUTING").
- :meth:`advance_escalations` walks every still-unacknowledged alert
  against its organization's own escalation policies and, where a
  further level has come due, notifies that level's own target and
  moves the alert to ``ESCALATED`` ("Automatic Escalation",
  "Time-based Escalation").

An escalation level of type ``ONCALL_SCHEDULE`` resolves through
:mod:`app.escalation.oncall`; ``USER``/``ROLE``/``MANAGER`` are
delivered to the level's own ``target_reference`` directly.

**Honest gap**: a ``WORKFLOW`` escalation level cannot currently run.
Launching a remediation workflow needs a caller token
(:meth:`app.clients.workflow_client.WorkflowRuntimeClient.execute_workflow`
requires one), and a scheduler-fired escalation pass has no caller --
the same platform-wide "no service-account credential mechanism exists
yet" gap every prior AI-IOS service has documented for its own
scheduled work. Such a level is recorded as escalated and logged, not
silently treated as if a workflow had run.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from shared_core.logging.logger import get_logger

from app.escalation.engine import EscalationLevel
from app.events.alert_events import AlertEscalatedEvent
from app.models.alert_instance import AlertInstance
from app.models.enums import AlertStatus, EscalationTargetType
from app.notifications.alert_notifications import AlertNotificationService
from app.repositories.alert_instance import AlertInstanceRepository
from app.services.alert import AlertService
from app.services.escalation import AlertEscalationPolicyService
from app.services.oncall import AlertOnCallScheduleService
from app.services.route import AlertRouteService
from app.types import EventPublisher

logger = get_logger("app.services.dispatch")

_UNACKNOWLEDGED_STATUSES = frozenset({AlertStatus.NEW, AlertStatus.OPEN})
"""Only a genuinely unattended alert escalates.

Once someone has acknowledged or started investigating, further
automatic escalation would page people about work already underway.
"""


class AlertDispatchService:
    """Fans alerts out to routes and advances escalation policies."""

    def __init__(
        self,
        alerts: AlertService,
        alert_repository: AlertInstanceRepository,
        routes: AlertRouteService,
        policies: AlertEscalationPolicyService,
        oncall: AlertOnCallScheduleService,
        notifications: AlertNotificationService,
        *,
        publish_event: EventPublisher,
    ) -> None:
        self._alerts = alerts
        self._alert_repository = alert_repository
        self._routes = routes
        self._policies = policies
        self._oncall = oncall
        self._notifications = notifications
        self._publish_event = publish_event

    async def dispatch_alert(self, alert: AlertInstance) -> int:
        """Deliver *alert* through every matching route. Returns the count."""
        matching = await self._routes.select_for_severity(alert.organization_id, alert.severity)
        for route in matching:
            await self._notifications.deliver(alert, route)
        return len(matching)

    async def advance_escalations(
        self, organization_id: UUID, *, moment: datetime | None = None
    ) -> int:
        """Advance every due escalation for *organization_id*. Returns the count."""
        now = moment or datetime.now(UTC)
        policies = await self._policies.list_enabled_for_org(organization_id)
        if not policies:
            return 0

        open_alerts = [
            alert
            for alert in await self._alert_repository.list_open_for_org(organization_id)
            if alert.status in _UNACKNOWLEDGED_STATUSES
        ]

        escalated = 0
        for alert in open_alerts:
            for policy in policies:
                level = self._policies.due_level_for_alert(policy, alert, moment=now)
                if level is None:
                    continue
                await self._escalate(alert, level)
                escalated += 1
                break
        return escalated

    async def _escalate(self, alert: AlertInstance, level: EscalationLevel) -> None:
        target = await self._resolve_target(level)
        if target is None:
            logger.warning(
                "Escalation level could not be delivered.",
                extra={
                    "extra_fields": {
                        "alert_id": str(alert.id),
                        "target_type": str(level.target_type),
                        "target_reference": level.target_reference,
                    }
                },
            )
        else:
            for route in await self._routes.select_for_severity(
                alert.organization_id, alert.severity
            ):
                await self._notifications.deliver(alert, route)

        await self._alerts.transition(
            alert.id,
            AlertStatus.ESCALATED,
            reason=f"Escalated to level {level.sequence} ({level.target_type!s}).",
        )
        await self._publish_event(
            AlertEscalatedEvent(
                source_service="alerting-service",
                payload={
                    "alert_id": str(alert.id),
                    "level": level.sequence,
                    "target_type": str(level.target_type),
                    "target_reference": target or level.target_reference,
                },
            )
        )

    async def _resolve_target(self, level: EscalationLevel) -> str | None:
        """Resolve a level's own target to a concrete recipient, if possible."""
        if level.target_type is EscalationTargetType.ONCALL_SCHEDULE:
            try:
                return await self._oncall.current_oncall(UUID(level.target_reference))
            except ValueError:
                return None
        if level.target_type is EscalationTargetType.WORKFLOW:
            # See this module's own docstring: no caller token exists for
            # a scheduler-fired pass, so a workflow level cannot run.
            return None
        return level.target_reference


__all__ = ["AlertDispatchService"]
