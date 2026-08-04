"""Firing the escalation ladder against breaching and breached SLAs.

Wraps ``app/escalation/engine.py`` with the database, the clock, and
notifications.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.exceptions.conflict import ConflictError
from shared_core.logging.logger import get_logger

from app.escalation.engine import EscalationStep, default_policy_for, due_steps, manual_step
from app.events.incident_events import SOURCE_SERVICE, IncidentEscalatedEvent
from app.models.enums import (
    EscalationStatus,
    IncidentPriority,
    SlaStatus,
    escalation_status_of,
)
from app.models.sla import IncidentEscalation
from app.notifications.incident_notifications import IncidentNotificationService
from app.repositories.incident import IncidentRepository
from app.repositories.sla import EscalationRepository, SlaRepository
from app.types import EventPublisher

logger = get_logger("app.services.escalation")


class EscalationService:
    """Escalation: policy evaluation, manual overrides, acknowledgement."""

    def __init__(
        self,
        escalations: EscalationRepository,
        slas: SlaRepository,
        incidents: IncidentRepository,
        notifications: IncidentNotificationService,
        *,
        publish_event: EventPublisher | None = None,
        max_levels: int = 3,
    ) -> None:
        self._escalations = escalations
        self._slas = slas
        self._incidents = incidents
        self._notifications = notifications
        self._publish = publish_event
        self._max_levels = max_levels

    async def _publish_event(self, event: Any) -> None:
        if self._publish is not None:
            await self._publish(event)

    async def _fire(
        self,
        organization_id: UUID,
        incident_id: UUID,
        step: EscalationStep,
        *,
        reason: str,
        sla_id: UUID | None,
        actor_id: UUID | None,
        now: datetime,
    ) -> IncidentEscalation:
        created = await self._escalations.create(
            IncidentEscalation(
                organization_id=organization_id,
                incident_id=incident_id,
                sla_id=sla_id,
                trigger=step.trigger,
                status=EscalationStatus.TRIGGERED,
                level=step.level,
                escalate_to_id=step.target_id,
                escalate_to_role=step.target_role,
                reason=reason,
                triggered_at=now,
                created_by=actor_id,
            )
        )
        incident = await self._incidents.require_in_org(organization_id, incident_id)
        incident.escalation_count += 1
        await self._incidents.update(incident)

        await self._publish_event(
            IncidentEscalatedEvent(
                source_service=SOURCE_SERVICE,
                payload={
                    "organization_id": str(organization_id),
                    "incident_id": str(incident_id),
                    "level": step.level,
                    "reason": reason,
                },
            )
        )
        if step.target_id:
            await self._notifications.send_escalation(
                step.target_id,
                reference=incident.reference,
                title=incident.title,
                level=step.level,
                reason=reason,
            )
        return created

    async def evaluate_incident(
        self,
        organization_id: UUID,
        incident_id: UUID,
        *,
        priority: IncidentPriority,
        now: datetime | None = None,
    ) -> list[IncidentEscalation]:
        """Fire every escalation rung that has come due since the last check.

        Anchored on the earliest breach among the incident's clocks --
        the ladder starts counting from the first thing that actually
        went wrong, not from whenever this method happens to be called.
        Every overdue rung fires in one pass, so a delayed sweep catches
        up rather than escalating one level per tick.
        """
        moment = now or datetime.now(UTC)
        breached = [
            row
            for row in await self._slas.list_for_incident(organization_id, incident_id)
            if row.status == str(SlaStatus.BREACHED) and row.breached_at is not None
        ]
        if not breached:
            return []
        anchor = min(row.breached_at for row in breached if row.breached_at is not None)

        policy = default_policy_for(priority, max_levels=self._max_levels)
        fired_levels = await self._escalations.fired_levels(organization_id, incident_id)
        steps = due_steps(policy, anchor=anchor, now=moment, already_fired_levels=fired_levels)

        return [
            await self._fire(
                organization_id,
                incident_id,
                step,
                reason=f"Escalation policy level {step.level} for priority {priority!s}.",
                sla_id=breached[0].id,
                actor_id=None,
                now=moment,
            )
            for step in steps
        ]

    async def escalate_manually(
        self,
        organization_id: UUID,
        incident_id: UUID,
        *,
        target_id: str,
        reason: str,
        actor_id: UUID | None = None,
        now: datetime | None = None,
    ) -> IncidentEscalation:
        """A one-off escalation outside any policy ladder.

        The level assigned is one past whatever has already fired, so a
        manual escalation never collides with -- or is mistaken for -- a
        policy-driven one at the same level.
        """
        fired = await self._escalations.fired_levels(organization_id, incident_id)
        next_level = max(fired, default=0) + 1
        step = manual_step(level=next_level, target_id=target_id, reason=reason)
        return await self._fire(
            organization_id,
            incident_id,
            step,
            reason=reason,
            sla_id=None,
            actor_id=actor_id,
            now=now or datetime.now(UTC),
        )

    async def acknowledge(
        self, organization_id: UUID, escalation_id: UUID, *, now: datetime | None = None
    ) -> IncidentEscalation:
        """Acknowledge a fired escalation.

        Raises:
            ConflictError: If it has not fired, or was cancelled.
        """
        row = await self._escalations.require_in_org(organization_id, escalation_id)
        if escalation_status_of(row.status) is not EscalationStatus.TRIGGERED:
            raise ConflictError(f"Escalation {escalation_id} is {row.status!s}, not triggered.")
        row.status = EscalationStatus.ACKNOWLEDGED
        row.acknowledged_at = now or datetime.now(UTC)
        return await self._escalations.update(row)

    async def cancel(
        self, organization_id: UUID, escalation_id: UUID, *, reason: str
    ) -> IncidentEscalation:
        """Cancel a pending or triggered escalation.

        Raises:
            ConflictError: If it has already been acknowledged or cancelled.
        """
        row = await self._escalations.require_in_org(organization_id, escalation_id)
        if escalation_status_of(row.status) in (
            EscalationStatus.ACKNOWLEDGED,
            EscalationStatus.CANCELLED,
        ):
            raise ConflictError(
                f"Escalation {escalation_id} is {row.status!s} and cannot be cancelled."
            )
        row.status = EscalationStatus.CANCELLED
        row.cancelled_reason = reason
        return await self._escalations.update(row)

    async def list_for_incident(
        self, organization_id: UUID, incident_id: UUID
    ) -> list[IncidentEscalation]:
        """Every escalation on one incident."""
        return await self._escalations.list_for_incident(organization_id, incident_id)


__all__ = ["EscalationService"]
