"""Incident creation, correlation, lifecycle, assignment, and merging.

The core service. Every write here goes through the pure decisions in
``app/incidents/engine.py`` -- this module supplies the database, the
clock, and the event bus around them.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.validation import ValidationError
from shared_core.logging.logger import get_logger

from app.events.incident_events import (
    SOURCE_SERVICE,
    IncidentAssignedEvent,
    IncidentClosedEvent,
    IncidentCreatedEvent,
    IncidentReopenedEvent,
    IncidentResolvedEvent,
)
from app.incidents.engine import (
    compute_durations,
    correlates,
    is_reopen,
    validate_transition,
)
from app.incidents.engine import (
    fingerprint as compute_fingerprint,
)
from app.models.enums import (
    AssignmentMethod,
    IncidentCategory,
    IncidentPriority,
    IncidentSource,
    IncidentStatus,
    TimelineEventKind,
    incident_status_of,
)
from app.models.incident import Incident
from app.models.timeline import IncidentAssignment, IncidentTimeline, IncidentWorklog
from app.notifications.incident_notifications import IncidentNotificationService
from app.repositories.incident import IncidentRepository
from app.repositories.timeline import AssignmentRepository, TimelineRepository, WorklogRepository
from app.types import EventPublisher

logger = get_logger("app.services.incident")


class IncidentService:
    """Incidents: creation, correlation, lifecycle, assignment, merging."""

    def __init__(
        self,
        incidents: IncidentRepository,
        timelines: TimelineRepository,
        worklogs: WorklogRepository,
        assignments: AssignmentRepository,
        notifications: IncidentNotificationService,
        *,
        publish_event: EventPublisher | None = None,
        correlation_window_minutes: int = 15,
    ) -> None:
        self._incidents = incidents
        self._timelines = timelines
        self._worklogs = worklogs
        self._assignments = assignments
        self._notifications = notifications
        self._publish = publish_event
        self._correlation_window_minutes = correlation_window_minutes

    async def _publish_event(self, event: Any) -> None:
        if self._publish is not None:
            await self._publish(event)

    async def _timeline_entry(
        self,
        organization_id: UUID,
        incident_id: UUID,
        *,
        kind: TimelineEventKind,
        summary: str,
        actor_id: str | None,
        details: dict[str, Any] | None = None,
        now: datetime,
    ) -> None:
        await self._timelines.create(
            IncidentTimeline(
                organization_id=organization_id,
                incident_id=incident_id,
                kind=kind,
                summary=summary,
                actor_id=actor_id,
                occurred_at=now,
                details=details or {},
            )
        )

    async def create(
        self,
        organization_id: UUID,
        *,
        title: str,
        description: str | None = None,
        source: IncidentSource = IncidentSource.MANUAL,
        source_reference: str | None = None,
        category: IncidentCategory = IncidentCategory.CUSTOM,
        priority: IncidentPriority = IncidentPriority.P3_MEDIUM,
        correlation_key: str | None = None,
        tags: list[str] | None = None,
        actor_id: UUID | None = None,
        now: datetime | None = None,
    ) -> tuple[Incident, bool]:
        """Open an incident, or correlate onto an existing open one.

        Returns the incident and whether it is newly created.

        **Correlation is the point.** A recurring firing against the
        same underlying condition must not open a fresh incident on
        every polling interval -- see ``app/incidents/engine.py
        ::correlates`` for the three conditions that gate it.
        """
        moment = now or datetime.now(UTC)
        new_fingerprint = (
            compute_fingerprint(source=str(source), category=str(category), key=correlation_key)
            if correlation_key is not None
            else None
        )

        if new_fingerprint is not None:
            candidates = await self._incidents.find_open_by_fingerprint(
                organization_id, new_fingerprint
            )
            for candidate in candidates:
                last_activity = candidate.updated_at or candidate.created_at
                if correlates(
                    existing_fingerprint=new_fingerprint,
                    new_fingerprint=new_fingerprint,
                    existing_status=incident_status_of(candidate.status),
                    existing_last_activity=last_activity,
                    now=moment,
                    window_minutes=self._correlation_window_minutes,
                ):
                    await self._timeline_entry(
                        organization_id,
                        candidate.id,
                        kind=TimelineEventKind.SYSTEM,
                        summary=f"A recurring firing correlated onto this incident: {title!r}.",
                        actor_id=str(actor_id) if actor_id else None,
                        now=moment,
                    )
                    candidate.updated_by = actor_id
                    await self._incidents.update(candidate)
                    return candidate, False

        sequence = await self._incidents.next_reference_sequence(organization_id)
        created = await self._incidents.create(
            Incident(
                organization_id=organization_id,
                reference=f"INC-{sequence:04d}",
                title=title,
                description=description,
                source=source,
                source_reference=source_reference,
                category=category,
                priority=priority,
                status=IncidentStatus.NEW,
                fingerprint=new_fingerprint,
                detected_at=moment,
                tags=list(tags or []),
                created_by=actor_id,
            )
        )
        await self._timeline_entry(
            organization_id,
            created.id,
            kind=TimelineEventKind.CREATED,
            summary=f"Incident opened: {title!r} (priority {priority!s}, source {source!s}).",
            actor_id=str(actor_id) if actor_id else None,
            now=moment,
        )
        await self._publish_event(
            IncidentCreatedEvent(
                source_service=SOURCE_SERVICE,
                payload={
                    "organization_id": str(organization_id),
                    "incident_id": str(created.id),
                    "reference": created.reference,
                    "priority": str(priority),
                    "category": str(category),
                    "source": str(source),
                },
            )
        )
        return created, True

    async def get(self, organization_id: UUID, incident_id: UUID) -> Incident:
        """One incident.

        Raises:
            NotFoundError: If it does not exist here.
        """
        return await self._incidents.require_in_org(organization_id, incident_id)

    async def list_incidents(
        self,
        organization_id: UUID,
        *,
        status: IncidentStatus | None = None,
        priority: IncidentPriority | None = None,
        category: IncidentCategory | None = None,
        assignee_id: str | None = None,
        is_major: bool | None = None,
        open_only: bool = False,
        limit: int = 200,
        offset: int = 0,
    ) -> list[Incident]:
        """Incidents matching a caller's filters."""
        return await self._incidents.list_filtered(
            organization_id,
            status=status,
            priority=priority,
            category=category,
            assignee_id=assignee_id,
            is_major=is_major,
            open_only=open_only,
            limit=limit,
            offset=offset,
        )

    async def transition(
        self,
        organization_id: UUID,
        incident_id: UUID,
        *,
        target: IncidentStatus,
        note: str | None = None,
        actor_id: UUID | None = None,
        now: datetime | None = None,
    ) -> Incident:
        """Move an incident through its lifecycle.

        Raises:
            ValidationError: If *target* is not reachable from the
                incident's current status.
        """
        moment = now or datetime.now(UTC)
        stored = await self._incidents.require_in_org(organization_id, incident_id)
        current = incident_status_of(stored.status)
        validate_transition(current, target)

        reopening = is_reopen(current, target)
        stored.status = target
        stored.updated_by = actor_id

        if target is IncidentStatus.ACKNOWLEDGED and stored.acknowledged_at is None:
            stored.acknowledged_at = moment
        if target is IncidentStatus.RESOLVED:
            stored.resolved_at = moment
        if target is IncidentStatus.CLOSED:
            stored.closed_at = moment
        if reopening:
            stored.reopen_count += 1
            stored.resolved_at = None
            stored.closed_at = None

        durations = compute_durations(
            detected_at=stored.detected_at,
            acknowledged_at=stored.acknowledged_at,
            resolved_at=stored.resolved_at,
        )
        stored.mtta_seconds = durations.mtta_seconds
        stored.mttr_seconds = durations.mttr_seconds

        updated = await self._incidents.update(stored)
        await self._timeline_entry(
            organization_id,
            incident_id,
            kind=TimelineEventKind.STATUS_CHANGE,
            summary=(
                f"Reopened: moved from {current!s} back to {target!s}."
                if reopening
                else f"Status changed from {current!s} to {target!s}."
            )
            + (f" {note}" if note else ""),
            actor_id=str(actor_id) if actor_id else None,
            details={"from": str(current), "to": str(target), "reopen": reopening},
            now=moment,
        )

        if reopening:
            await self._publish_event(
                IncidentReopenedEvent(
                    source_service=SOURCE_SERVICE,
                    payload={
                        "organization_id": str(organization_id),
                        "incident_id": str(incident_id),
                        "from_status": str(current),
                    },
                )
            )
        elif target is IncidentStatus.RESOLVED:
            await self._publish_event(
                IncidentResolvedEvent(
                    source_service=SOURCE_SERVICE,
                    payload={
                        "organization_id": str(organization_id),
                        "incident_id": str(incident_id),
                        "mttr_seconds": updated.mttr_seconds,
                    },
                )
            )
            if updated.assignee_id:
                await self._notifications.send_resolution(
                    updated.assignee_id, reference=updated.reference, title=updated.title
                )
        elif target is IncidentStatus.CLOSED:
            await self._publish_event(
                IncidentClosedEvent(
                    source_service=SOURCE_SERVICE,
                    payload={
                        "organization_id": str(organization_id),
                        "incident_id": str(incident_id),
                    },
                )
            )

        return updated

    async def assign(
        self,
        organization_id: UUID,
        incident_id: UUID,
        *,
        assignee_id: str,
        assignee_team: str | None = None,
        method: AssignmentMethod = AssignmentMethod.MANUAL,
        reason: str | None = None,
        actor_id: UUID | None = None,
        now: datetime | None = None,
    ) -> Incident:
        """Assign or reassign an incident, closing the prior assignment."""
        moment = now or datetime.now(UTC)
        stored = await self._incidents.require_in_org(organization_id, incident_id)

        current = await self._assignments.current(organization_id, incident_id)
        if current is not None:
            current.unassigned_at = moment
            await self._assignments.update(current)

        await self._assignments.create(
            IncidentAssignment(
                organization_id=organization_id,
                incident_id=incident_id,
                assignee_id=assignee_id,
                assignee_team=assignee_team,
                method=method,
                assigned_by=str(actor_id) if actor_id else None,
                assigned_at=moment,
                reason=reason,
            )
        )

        stored.assignee_id = assignee_id
        stored.assignee_team = assignee_team
        stored.assignment_method = str(method)
        if incident_status_of(stored.status) is IncidentStatus.NEW:
            stored.status = IncidentStatus.ASSIGNED
            stored.responded_at = stored.responded_at or moment
        stored.updated_by = actor_id
        updated = await self._incidents.update(stored)

        await self._timeline_entry(
            organization_id,
            incident_id,
            kind=TimelineEventKind.ASSIGNMENT,
            summary=f"Assigned to {assignee_id} ({method!s}).",
            actor_id=str(actor_id) if actor_id else None,
            details={"assignee_id": assignee_id, "method": str(method)},
            now=moment,
        )
        await self._publish_event(
            IncidentAssignedEvent(
                source_service=SOURCE_SERVICE,
                payload={
                    "organization_id": str(organization_id),
                    "incident_id": str(incident_id),
                    "assignee_id": assignee_id,
                    "method": str(method),
                },
            )
        )
        await self._notifications.send_assignment(
            assignee_id, reference=updated.reference, title=updated.title, method=str(method)
        )
        return updated

    async def merge(
        self,
        organization_id: UUID,
        *,
        source_incident_id: UUID,
        target_incident_id: UUID,
        reason: str,
        actor_id: UUID | None = None,
        now: datetime | None = None,
    ) -> Incident:
        """Merge one incident into another.

        Raises:
            ValidationError: If the two ids are the same, or the target
                is itself already merged into something else.
            ConflictError: If the source is not in a state that may be
                merged (already terminal).
        """
        if source_incident_id == target_incident_id:
            raise ValidationError("An incident cannot be merged into itself.")
        moment = now or datetime.now(UTC)

        source = await self._incidents.require_in_org(organization_id, source_incident_id)
        target = await self._incidents.require_in_org(organization_id, target_incident_id)
        if target.merged_into_id is not None:
            raise ValidationError(
                f"{target.reference} is itself merged into another incident; "
                "merge into that one instead."
            )
        current = incident_status_of(source.status)
        if current in (IncidentStatus.CLOSED, IncidentStatus.CANCELLED, IncidentStatus.MERGED):
            raise ConflictError(f"{source.reference} is {current!s} and cannot be merged.")

        source.status = IncidentStatus.MERGED
        source.merged_into_id = target.id
        source.updated_by = actor_id
        updated_source = await self._incidents.update(source)

        await self._timeline_entry(
            organization_id,
            source.id,
            kind=TimelineEventKind.MERGE,
            summary=f"Merged into {target.reference}: {reason}",
            actor_id=str(actor_id) if actor_id else None,
            details={"merged_into": str(target.id)},
            now=moment,
        )
        await self._timeline_entry(
            organization_id,
            target.id,
            kind=TimelineEventKind.MERGE,
            summary=f"Absorbed {source.reference}: {reason}",
            actor_id=str(actor_id) if actor_id else None,
            details={"merged_from": str(source.id)},
            now=moment,
        )
        return updated_source

    async def add_worklog(
        self,
        organization_id: UUID,
        incident_id: UUID,
        *,
        note: str,
        kind: str = "other",
        minutes_spent: int | None = None,
        author_id: UUID | None = None,
        now: datetime | None = None,
    ) -> IncidentWorklog:
        """Record effort spent on an incident."""
        await self._incidents.require_in_org(organization_id, incident_id)
        moment = now or datetime.now(UTC)
        return await self._worklogs.create(
            IncidentWorklog(
                organization_id=organization_id,
                incident_id=incident_id,
                kind=kind,
                author_id=str(author_id) if author_id else None,
                note=note,
                minutes_spent=minutes_spent,
                logged_at=moment,
                created_by=author_id,
            )
        )

    async def add_note(
        self,
        organization_id: UUID,
        incident_id: UUID,
        *,
        summary: str,
        actor_id: UUID | None = None,
        now: datetime | None = None,
    ) -> None:
        """Add a free-text note to an incident's timeline."""
        await self._incidents.require_in_org(organization_id, incident_id)
        await self._timeline_entry(
            organization_id,
            incident_id,
            kind=TimelineEventKind.NOTE,
            summary=summary,
            actor_id=str(actor_id) if actor_id else None,
            now=now or datetime.now(UTC),
        )

    async def timeline(self, organization_id: UUID, incident_id: UUID) -> list[IncidentTimeline]:
        """One incident's full timeline, oldest first."""
        await self._incidents.require_in_org(organization_id, incident_id)
        return await self._timelines.list_for_incident(organization_id, incident_id)

    async def worklogs(self, organization_id: UUID, incident_id: UUID) -> list[IncidentWorklog]:
        """One incident's worklog entries, oldest first."""
        await self._incidents.require_in_org(organization_id, incident_id)
        return await self._worklogs.list_for_incident(organization_id, incident_id)


__all__ = ["IncidentService"]
