"""SLA clocks: starting them, pausing them, and sweeping for breaches.

Wraps ``app/sla/engine.py`` with the database and the clock. The engine
decides what a breach or a due date *is*; this module decides when to
compute one and what to do about it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError
from shared_core.logging.logger import get_logger

from app.models.enums import (
    DEFAULT_SLA_MINUTES,
    IncidentPriority,
    SlaKind,
    SlaStatus,
    sla_status_of,
)
from app.models.sla import IncidentSla
from app.notifications.incident_notifications import IncidentNotificationService
from app.repositories.catalogue import IncidentPriorityRepository
from app.repositories.incident import IncidentRepository
from app.repositories.sla import SlaRepository
from app.sla.engine import (
    ALWAYS_OPEN,
    BusinessCalendar,
    ClockState,
    compliance_rate,
    due_at_for,
    elapsed_seconds,
    is_breached,
    resume_paused_seconds,
    should_warn,
)
from app.types import EventPublisher

logger = get_logger("app.services.sla")


def _state_of(row: IncidentSla) -> ClockState:
    return ClockState(
        started_at=row.started_at,
        due_at=row.due_at,
        paused_at=row.paused_at,
        paused_seconds_total=row.paused_seconds_total,
        met_at=row.met_at,
        breached_at=row.breached_at,
    )


class SlaService:
    """SLA clock lifecycle: start, pause, resume, meet, breach, sweep."""

    def __init__(
        self,
        slas: SlaRepository,
        priorities: IncidentPriorityRepository,
        incidents: IncidentRepository,
        notifications: IncidentNotificationService,
        *,
        publish_event: EventPublisher | None = None,
        calendar: BusinessCalendar | None = None,
        warning_percent: int = 80,
    ) -> None:
        self._slas = slas
        self._priorities = priorities
        self._incidents = incidents
        self._notifications = notifications
        self._publish = publish_event
        self._calendar = calendar or BusinessCalendar()
        self._warning_percent = warning_percent

    async def _publish_event(self, event: Any) -> None:
        if self._publish is not None:
            await self._publish(event)

    async def _target_minutes(
        self, organization_id: UUID, priority: IncidentPriority, kind: SlaKind
    ) -> int | None:
        """An organization's override for this priority/kind, or the platform default."""
        override = await self._priorities.get_for_priority(organization_id, priority)
        if override is not None:
            column = {
                SlaKind.RESPONSE: override.response_sla_minutes,
                SlaKind.ACKNOWLEDGEMENT: override.acknowledgement_sla_minutes,
                SlaKind.RESOLUTION: override.resolution_sla_minutes,
            }.get(kind)
            if column is not None:
                return column
        return DEFAULT_SLA_MINUTES.get(priority, {}).get(kind)

    async def start_clocks(
        self,
        organization_id: UUID,
        incident_id: UUID,
        *,
        priority: IncidentPriority,
        is_24x7: bool = True,
        now: datetime | None = None,
    ) -> list[IncidentSla]:
        """Start every configured clock for a newly created incident.

        A clock with no configured target -- ``DEFAULT_SLA_MINUTES``
        deliberately has no entry for escalation SLAs -- is skipped
        rather than started with an invented target. A clock that would
        never breach against a made-up number is worse than no clock:
        it looks like a real commitment on a dashboard and is not one.
        """
        moment = now or datetime.now(UTC)
        calendar = ALWAYS_OPEN if is_24x7 else self._calendar
        created: list[IncidentSla] = []
        for kind in (SlaKind.RESPONSE, SlaKind.ACKNOWLEDGEMENT, SlaKind.RESOLUTION):
            target = await self._target_minutes(organization_id, priority, kind)
            if target is None:
                continue
            due = due_at_for(moment, target, is_24x7=is_24x7, calendar=calendar)
            row = await self._slas.create(
                IncidentSla(
                    organization_id=organization_id,
                    incident_id=incident_id,
                    kind=kind,
                    status=SlaStatus.RUNNING,
                    target_minutes=target,
                    is_24x7=is_24x7,
                    started_at=moment,
                    due_at=due,
                )
            )
            created.append(row)
        return created

    async def mark_met(
        self,
        organization_id: UUID,
        incident_id: UUID,
        kind: SlaKind,
        *,
        now: datetime | None = None,
    ) -> IncidentSla | None:
        """Stop a clock as met, if it is still running.

        A clock not currently running -- already met, already breached,
        or never started -- is left untouched rather than raising: the
        caller (an incident transitioning to acknowledged, say) should
        not have to know or care whether the clock happened to exist.
        """
        row = await self._slas.get_for_incident(organization_id, incident_id, kind)
        if row is None or sla_status_of(row.status) is not SlaStatus.RUNNING:
            return row
        row.met_at = now or datetime.now(UTC)
        row.status = SlaStatus.MET
        return await self._slas.update(row)

    async def pause(
        self,
        organization_id: UUID,
        sla_id: UUID,
        *,
        reason: str,
        now: datetime | None = None,
    ) -> IncidentSla:
        """Pause a running clock.

        Raises:
            ConflictError: If the clock is not currently running.
        """
        row = await self._slas.require_in_org(organization_id, sla_id)
        if sla_status_of(row.status) is not SlaStatus.RUNNING:
            raise ConflictError(f"SLA clock {sla_id} is {row.status!s}, not running; cannot pause.")
        row.paused_at = now or datetime.now(UTC)
        row.status = SlaStatus.PAUSED
        row.pause_reason = reason
        return await self._slas.update(row)

    async def resume(
        self, organization_id: UUID, sla_id: UUID, *, now: datetime | None = None
    ) -> IncidentSla:
        """Resume a paused clock.

        Raises:
            ConflictError: If the clock is not currently paused.
            NotFoundError: If the clock has no recorded pause start, which
                should be unreachable for a row in ``PAUSED`` status.
        """
        row = await self._slas.require_in_org(organization_id, sla_id)
        if sla_status_of(row.status) is not SlaStatus.PAUSED or row.paused_at is None:
            raise ConflictError(f"SLA clock {sla_id} is not currently paused.")
        moment = now or datetime.now(UTC)
        row.paused_seconds_total += resume_paused_seconds(
            paused_at=row.paused_at, resumed_at=moment
        )
        row.paused_at = None
        row.status = SlaStatus.RUNNING
        return await self._slas.update(row)

    async def list_for_incident(
        self, organization_id: UUID, incident_id: UUID
    ) -> list[IncidentSla]:
        """Every SLA clock on one incident."""
        return await self._slas.list_for_incident(organization_id, incident_id)

    async def sweep(self, organization_id: UUID, *, now: datetime | None = None) -> dict[str, int]:
        """Check every running clock for warnings and breaches.

        Returns counts, for the worker to log. Every clock is evaluated
        independently -- one clock erroring must not stop the sweep from
        checking the rest, since the whole point of a sweep is that it
        covers the entire open estate on one pass.
        """
        moment = now or datetime.now(UTC)
        warned = breached = 0
        for row in await self._slas.list_running(organization_id):
            state = _state_of(row)
            try:
                if not row.warning_sent_at and should_warn(
                    state, now=moment, warning_percent=self._warning_percent
                ):
                    row.warning_sent_at = moment
                    await self._slas.update(row)
                    warned += 1
                if is_breached(state, now=moment):
                    row.breached_at = moment
                    row.status = SlaStatus.BREACHED
                    await self._slas.update(row)
                    breached += 1
                    incident = await self._incidents.require_in_org(
                        organization_id, row.incident_id
                    )
                    if incident.assignee_id:
                        await self._notifications.send_sla_breach(
                            incident.assignee_id,
                            reference=incident.reference,
                            title=incident.title,
                            sla_kind=str(row.kind),
                        )
            except NotFoundError:
                logger.warning(
                    "SLA clock references an incident that no longer exists.",
                    extra={"extra_fields": {"sla_id": str(row.id)}},
                )
        return {"warned": warned, "breached": breached}

    async def elapsed_for(self, row: IncidentSla, *, now: datetime | None = None) -> float:
        """Seconds actually run on one clock, excluding pauses."""
        return elapsed_seconds(_state_of(row), now=now or datetime.now(UTC))

    async def compliance_summary(
        self, organization_id: UUID, *, start: datetime, end: datetime
    ) -> dict[str, float]:
        """SLA compliance across a window, across every clock kind.

        One overall rate rather than one per :class:`SlaKind`: the
        repository counts by outcome (met/breached) within the window,
        not per kind, and a dashboard asking "are we meeting our SLAs"
        wants the single number that answers it.
        """
        met = await self._slas.count_in_window(
            organization_id, status=SlaStatus.MET, start=start, end=end
        )
        breached = await self._slas.count_in_window(
            organization_id, status=SlaStatus.BREACHED, start=start, end=end
        )
        return {
            "met": float(met),
            "breached": float(breached),
            "rate": compliance_rate(met=met, breached=breached),
        }


__all__ = ["SlaService"]
