"""Implementation: tasks, the run as a whole, and validation gates.

Wraps ``app/models/implementation.py``'s tables with the database, the
clock, and the change lifecycle -- starting a run is what moves a
change from ``READY`` to ``IN_PROGRESS``, and completing one moves it
through ``VALIDATION`` to ``COMPLETED``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError
from shared_core.logging.logger import get_logger

from app.changes.engine import validate_transition
from app.events.change_events import (
    SOURCE_SERVICE,
    ImplementationCompletedEvent,
    ImplementationStartedEvent,
)
from app.models.enums import (
    ChangeStatus,
    ChangeTaskStatus,
    ImplementationStatus,
    ValidationKind,
    ValidationStatus,
    change_status_of,
    change_task_status_of,
)
from app.models.implementation import ChangeImplementation, ChangeTask, ChangeValidation
from app.notifications.change_notifications import ChangeNotificationService
from app.repositories.change import ChangeRequestRepository
from app.repositories.implementation import (
    ChangeImplementationRepository,
    ChangeTaskRepository,
    ChangeValidationRepository,
)
from app.types import EventPublisher

logger = get_logger("app.services.implementation")


class ImplementationService:
    """Implementation tasks, runs, and validation gates."""

    def __init__(
        self,
        tasks: ChangeTaskRepository,
        runs: ChangeImplementationRepository,
        validations: ChangeValidationRepository,
        changes: ChangeRequestRepository,
        notifications: ChangeNotificationService,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._tasks = tasks
        self._runs = runs
        self._validations = validations
        self._changes = changes
        self._notifications = notifications
        self._publish = publish_event

    async def _publish_event(self, event: Any) -> None:
        if self._publish is not None:
            await self._publish(event)

    async def add_task(
        self,
        organization_id: UUID,
        change_id: UUID,
        *,
        title: str,
        description: str | None = None,
        assignee_id: str | None = None,
        sequence: int | None = None,
    ) -> ChangeTask:
        """Add one implementation task to a change."""
        await self._changes.require_in_org(organization_id, change_id)
        if sequence is None:
            existing = await self._tasks.list_for_change(organization_id, change_id)
            sequence = len(existing)
        return await self._tasks.create(
            ChangeTask(
                organization_id=organization_id,
                change_id=change_id,
                sequence=sequence,
                title=title,
                description=description,
                assignee_id=assignee_id,
                status=ChangeTaskStatus.PENDING,
            )
        )

    async def list_tasks(self, organization_id: UUID, change_id: UUID) -> list[ChangeTask]:
        """Every task for one change, in execution order."""
        return await self._tasks.list_for_change(organization_id, change_id)

    async def complete_task(
        self, organization_id: UUID, task_id: UUID, *, evidence: dict[str, Any] | None = None
    ) -> ChangeTask:
        """Mark a task done."""
        row = await self._tasks.require_in_org(organization_id, task_id)
        row.status = ChangeTaskStatus.COMPLETED
        row.completed_at = datetime.now(UTC)
        if evidence is not None:
            row.evidence = evidence
        return await self._tasks.update(row)

    async def fail_task(
        self, organization_id: UUID, task_id: UUID, *, evidence: dict[str, Any] | None = None
    ) -> ChangeTask:
        """Mark a task failed."""
        row = await self._tasks.require_in_org(organization_id, task_id)
        row.status = ChangeTaskStatus.FAILED
        if evidence is not None:
            row.evidence = evidence
        return await self._tasks.update(row)

    async def start(
        self, organization_id: UUID, change_id: UUID, *, started_by: str | None = None
    ) -> ChangeImplementation:
        """Begin implementing a ready change.

        Raises:
            ValidationError: If the change is not ``READY``.
        """
        moment = datetime.now(UTC)
        stored = await self._changes.require_in_org(organization_id, change_id)
        validate_transition(change_status_of(stored.status), ChangeStatus.IN_PROGRESS)

        run = await self._runs.create(
            ChangeImplementation(
                organization_id=organization_id,
                change_id=change_id,
                status=ImplementationStatus.IN_PROGRESS,
                started_by=started_by,
                started_at=moment,
                timeline=[{"at": moment.isoformat(), "event": "implementation started"}],
            )
        )
        stored.status = ChangeStatus.IN_PROGRESS
        stored.actual_start_at = moment
        await self._changes.update(stored)

        if stored.technical_owner_id:
            await self._notifications.send_implementation_started(
                stored.technical_owner_id, reference=stored.reference, title=stored.title
            )
        await self._publish_event(
            ImplementationStartedEvent(
                source_service=SOURCE_SERVICE,
                payload={"organization_id": str(organization_id), "change_id": str(change_id)},
            )
        )
        return run

    async def record_validation(
        self,
        organization_id: UUID,
        change_id: UUID,
        *,
        kind: ValidationKind,
        status: ValidationStatus,
        summary: str | None = None,
        is_gate: bool = False,
        ran_by: str | None = None,
        evidence: dict[str, Any] | None = None,
        now: datetime | None = None,
    ) -> ChangeValidation:
        """Record one validation run against a change.

        A failing gate is recorded, not refused -- refusing to record a
        failure would hide the exact evidence a rollback decision needs.
        """
        moment = now or datetime.now(UTC)
        await self._changes.require_in_org(organization_id, change_id)
        created = await self._validations.create(
            ChangeValidation(
                organization_id=organization_id,
                change_id=change_id,
                kind=kind,
                status=status,
                summary=summary,
                is_gate=is_gate,
                ran_by=ran_by,
                ran_at=moment,
                evidence=dict(evidence or {}),
            )
        )
        if is_gate and status is ValidationStatus.FAILED:
            stored = await self._changes.require_in_org(organization_id, change_id)
            if stored.technical_owner_id:
                await self._notifications.send_validation_failed(
                    stored.technical_owner_id,
                    reference=stored.reference,
                    title=stored.title,
                    validation_kind=str(kind),
                )
        return created

    async def list_validations(
        self, organization_id: UUID, change_id: UUID
    ) -> list[ChangeValidation]:
        """Every validation run for one change."""
        return await self._validations.list_for_change(organization_id, change_id)

    async def move_to_validation(
        self, organization_id: UUID, change_id: UUID, *, actor_id: UUID | None = None
    ) -> ChangeImplementation:
        """Move a change from implementation into its post-change validation phase.

        Raises:
            ConflictError: If any task is still pending, in progress, or blocked.
            NotFoundError: If no implementation run has been started.
        """
        stored = await self._changes.require_in_org(organization_id, change_id)
        tasks = await self._tasks.list_for_change(organization_id, change_id)
        unfinished = [
            one
            for one in tasks
            if change_task_status_of(one.status)
            in (ChangeTaskStatus.PENDING, ChangeTaskStatus.IN_PROGRESS, ChangeTaskStatus.BLOCKED)
        ]
        if unfinished:
            raise ConflictError(
                f"{len(unfinished)} task(s) on {stored.reference} are not yet finished."
            )

        validate_transition(change_status_of(stored.status), ChangeStatus.VALIDATION)
        stored.status = ChangeStatus.VALIDATION
        stored.updated_by = actor_id
        await self._changes.update(stored)

        run = await self._require_run(organization_id, change_id)
        run.progress_percent = 100
        return await self._runs.update(run)

    async def complete(
        self, organization_id: UUID, change_id: UUID, *, actor_id: UUID | None = None
    ) -> ChangeImplementation:
        """Complete a change that has passed validation.

        Raises:
            ConflictError: If any gate validation for this change failed.
        """
        moment = datetime.now(UTC)
        stored = await self._changes.require_in_org(organization_id, change_id)
        validations = await self._validations.list_for_change(organization_id, change_id)
        failed_gates = [
            one for one in validations if one.is_gate and one.status == str(ValidationStatus.FAILED)
        ]
        if failed_gates:
            raise ConflictError(
                f"{stored.reference} has {len(failed_gates)} failed gate validation(s); "
                "cannot complete."
            )

        validate_transition(change_status_of(stored.status), ChangeStatus.COMPLETED)
        stored.status = ChangeStatus.COMPLETED
        stored.completed_at = moment
        stored.actual_end_at = moment
        if stored.actual_start_at is not None:
            stored.implementation_duration_seconds = (
                moment - stored.actual_start_at
            ).total_seconds()
        stored.updated_by = actor_id
        await self._changes.update(stored)

        run = await self._require_run(organization_id, change_id)
        run.status = ImplementationStatus.COMPLETED
        run.completed_at = moment
        run = await self._runs.update(run)

        if stored.technical_owner_id:
            await self._notifications.send_implementation_completed(
                stored.technical_owner_id,
                reference=stored.reference,
                title=stored.title,
                status="completed",
            )
        await self._publish_event(
            ImplementationCompletedEvent(
                source_service=SOURCE_SERVICE,
                payload={
                    "organization_id": str(organization_id),
                    "change_id": str(change_id),
                    "status": "completed",
                },
            )
        )
        return run

    async def _require_run(self, organization_id: UUID, change_id: UUID) -> ChangeImplementation:
        run = await self._runs.get_for_change(organization_id, change_id)
        if run is None:
            raise NotFoundError(f"No implementation run exists for change {change_id}.")
        return run


__all__ = ["ImplementationService"]
