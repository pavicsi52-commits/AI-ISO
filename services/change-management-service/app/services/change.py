"""Change creation, editing, lifecycle transitions, scheduling, and relationships.

The core service. Every write here goes through the pure decisions in
``app/changes/engine.py`` -- this module supplies the database, the
clock, and the event bus around them.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.validation import ValidationError
from shared_core.logging.logger import get_logger

from app.changes.engine import validate_transition
from app.events.change_events import (
    SOURCE_SERVICE,
    ChangeCreatedEvent,
    ChangeScheduledEvent,
    ChangeSubmittedEvent,
)
from app.models.change import ChangeRelationship, ChangeRequest
from app.models.enums import (
    ChangeCategory,
    ChangePriority,
    ChangeStatus,
    ChangeType,
    RelationshipKind,
    change_status_of,
)
from app.repositories.calendar import ChangeCalendarRepository
from app.repositories.change import ChangeRelationshipRepository, ChangeRequestRepository
from app.types import EventPublisher

logger = get_logger("app.services.change")

_EDITABLE_STATUSES = frozenset({ChangeStatus.DRAFT})


class ChangeService:
    """Changes: creation, editing, lifecycle, scheduling, relationships."""

    def __init__(
        self,
        changes: ChangeRequestRepository,
        relationships: ChangeRelationshipRepository,
        calendar: ChangeCalendarRepository,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._changes = changes
        self._relationships = relationships
        self._calendar = calendar
        self._publish = publish_event

    async def _publish_event(self, event: Any) -> None:
        if self._publish is not None:
            await self._publish(event)

    async def create(
        self,
        organization_id: UUID,
        *,
        title: str,
        requester_id: str,
        description: str | None = None,
        business_justification: str | None = None,
        business_owner_id: str | None = None,
        technical_owner_id: str | None = None,
        category: ChangeCategory = ChangeCategory.CUSTOM,
        change_type: ChangeType = ChangeType.NORMAL,
        priority: ChangePriority = ChangePriority.MEDIUM,
        affected_assets: list[str] | None = None,
        affected_services: list[str] | None = None,
        affected_applications: list[str] | None = None,
        implementation_plan: str | None = None,
        validation_plan: str | None = None,
        rollback_plan: str | None = None,
        incident_id: str | None = None,
        problem_id: str | None = None,
        known_error_id: str | None = None,
        tags: list[str] | None = None,
        actor_id: UUID | None = None,
    ) -> ChangeRequest:
        """Open a new change request, in ``DRAFT``."""
        sequence = await self._changes.next_reference_sequence(organization_id)
        created = await self._changes.create(
            ChangeRequest(
                organization_id=organization_id,
                reference=f"CHG-{sequence:04d}",
                title=title,
                description=description,
                business_justification=business_justification,
                requester_id=requester_id,
                business_owner_id=business_owner_id,
                technical_owner_id=technical_owner_id,
                category=category,
                change_type=change_type,
                priority=priority,
                status=ChangeStatus.DRAFT,
                affected_assets=list(affected_assets or []),
                affected_services=list(affected_services or []),
                affected_applications=list(affected_applications or []),
                implementation_plan=implementation_plan,
                validation_plan=validation_plan,
                rollback_plan=rollback_plan,
                incident_id=incident_id,
                problem_id=problem_id,
                known_error_id=known_error_id,
                tags=list(tags or []),
                created_by=actor_id,
            )
        )
        await self._publish_event(
            ChangeCreatedEvent(
                source_service=SOURCE_SERVICE,
                payload={
                    "organization_id": str(organization_id),
                    "change_id": str(created.id),
                    "reference": created.reference,
                    "change_type": str(change_type),
                    "category": str(category),
                },
            )
        )
        return created

    async def get(self, organization_id: UUID, change_id: UUID) -> ChangeRequest:
        """One change.

        Raises:
            NotFoundError: If it does not exist here.
        """
        return await self._changes.require_in_org(organization_id, change_id)

    async def list_changes(
        self,
        organization_id: UUID,
        *,
        status: ChangeStatus | None = None,
        priority: ChangePriority | None = None,
        category: ChangeCategory | None = None,
        technical_owner_id: str | None = None,
        open_only: bool = False,
        limit: int = 200,
        offset: int = 0,
    ) -> list[ChangeRequest]:
        """Changes matching a caller's filters."""
        return await self._changes.list_filtered(
            organization_id,
            status=status,
            priority=priority,
            category=category,
            technical_owner_id=technical_owner_id,
            open_only=open_only,
            limit=limit,
            offset=offset,
        )

    async def update(
        self,
        organization_id: UUID,
        change_id: UUID,
        *,
        actor_id: UUID | None = None,
        **fields: Any,
    ) -> ChangeRequest:
        """Edit a change's own content fields.

        Raises:
            ConflictError: If the change has moved past ``DRAFT`` --
                once submitted, its plan is the plan a risk assessment
                and an approval chain are about to be evaluated against,
                and silently rewriting it out from under them would
                invalidate a decision nobody re-made.
        """
        stored = await self._changes.require_in_org(organization_id, change_id)
        current = change_status_of(stored.status)
        if current not in _EDITABLE_STATUSES:
            raise ConflictError(
                f"{stored.reference} is {current!s} and can no longer be edited directly."
            )
        for field, value in fields.items():
            setattr(stored, field, value)
        stored.updated_by = actor_id
        return await self._changes.update(stored)

    async def submit(
        self, organization_id: UUID, change_id: UUID, *, actor_id: UUID | None = None
    ) -> ChangeRequest:
        """Submit a change for risk assessment and approval."""
        moment = datetime.now(UTC)
        updated = await self.transition(
            organization_id, change_id, target=ChangeStatus.SUBMITTED, actor_id=actor_id, now=moment
        )
        updated.submitted_at = moment
        updated = await self._changes.update(updated)
        await self._publish_event(
            ChangeSubmittedEvent(
                source_service=SOURCE_SERVICE,
                payload={"organization_id": str(organization_id), "change_id": str(change_id)},
            )
        )
        return updated

    async def transition(
        self,
        organization_id: UUID,
        change_id: UUID,
        *,
        target: ChangeStatus,
        actor_id: UUID | None = None,
        now: datetime | None = None,
    ) -> ChangeRequest:
        """Move a change through its lifecycle.

        The generic engine-backed move every specialised service (risk,
        approval, CAB, implementation, rollback) calls internally as its
        own work resolves, and what the API exposes directly for the
        moves that need no supporting record of their own --
        ``CANCELLED`` and ``REJECTED`` chief among them.

        Sets only the two timestamps that are unambiguous regardless of
        which caller drove the move -- ``completed_at`` and
        ``closed_at``. ``submitted_at``, ``approved_at``, and the actual
        implementation window are each set by the specific service whose
        own work the timestamp actually describes, alongside the
        duration it makes computable -- see
        ``ApprovalService``/``CabService`` and
        ``ImplementationService``/``RollbackService``.

        Raises:
            ValidationError: If *target* is not reachable from the
                change's current status.
        """
        moment = now or datetime.now(UTC)
        stored = await self._changes.require_in_org(organization_id, change_id)
        current = change_status_of(stored.status)
        validate_transition(current, target)

        stored.status = target
        stored.updated_by = actor_id
        if target is ChangeStatus.COMPLETED:
            stored.completed_at = moment
        if target is ChangeStatus.CLOSED:
            stored.closed_at = moment

        return await self._changes.update(stored)

    async def schedule(
        self,
        organization_id: UUID,
        change_id: UUID,
        *,
        calendar_entry_id: UUID,
        scheduled_start_at: datetime,
        scheduled_end_at: datetime,
        actor_id: UUID | None = None,
    ) -> ChangeRequest:
        """Book a change into a maintenance window and mark it scheduled.

        Raises:
            NotFoundError: If the calendar entry does not exist here.
            ValidationError: If the change is not eligible to schedule
                from its current status.
        """
        await self._calendar.require_in_org(organization_id, calendar_entry_id)
        stored = await self._changes.require_in_org(organization_id, change_id)
        current = change_status_of(stored.status)
        validate_transition(current, ChangeStatus.SCHEDULED)

        stored.calendar_entry_id = calendar_entry_id
        stored.scheduled_start_at = scheduled_start_at
        stored.scheduled_end_at = scheduled_end_at
        stored.status = ChangeStatus.SCHEDULED
        stored.updated_by = actor_id
        updated = await self._changes.update(stored)

        await self._publish_event(
            ChangeScheduledEvent(
                source_service=SOURCE_SERVICE,
                payload={
                    "organization_id": str(organization_id),
                    "change_id": str(change_id),
                    "scheduled_start_at": scheduled_start_at.isoformat(),
                    "scheduled_end_at": scheduled_end_at.isoformat(),
                },
            )
        )
        return updated

    async def mark_ready(
        self, organization_id: UUID, change_id: UUID, *, actor_id: UUID | None = None
    ) -> ChangeRequest:
        """Mark a scheduled change ready to implement."""
        return await self.transition(
            organization_id, change_id, target=ChangeStatus.READY, actor_id=actor_id
        )

    async def close(
        self, organization_id: UUID, change_id: UUID, *, actor_id: UUID | None = None
    ) -> ChangeRequest:
        """Close out a completed or rolled-back change."""
        return await self.transition(
            organization_id, change_id, target=ChangeStatus.CLOSED, actor_id=actor_id
        )

    async def link_relationship(
        self,
        organization_id: UUID,
        change_id: UUID,
        *,
        related_change_id: UUID,
        kind: RelationshipKind,
        note: str | None = None,
    ) -> ChangeRelationship:
        """Record how one change relates to another.

        Raises:
            ValidationError: If a change is related to itself.
            NotFoundError: If either change does not exist here.
        """
        if change_id == related_change_id:
            raise ValidationError("A change cannot be related to itself.")
        await self._changes.require_in_org(organization_id, change_id)
        await self._changes.require_in_org(organization_id, related_change_id)
        return await self._relationships.create(
            ChangeRelationship(
                organization_id=organization_id,
                change_id=change_id,
                related_change_id=related_change_id,
                kind=kind,
                note=note,
            )
        )

    async def list_relationships(
        self, organization_id: UUID, change_id: UUID
    ) -> list[ChangeRelationship]:
        """Every relationship this change is the source side of."""
        return await self._relationships.list_for_change(organization_id, change_id)


__all__ = ["ChangeService"]
