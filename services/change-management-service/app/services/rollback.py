"""Rollback: planning, approving, and executing the undo of a change that did not hold.

A rollback's own status (``PLANNED``/``IN_PROGRESS``/``COMPLETED``/
``FAILED``) tracks the rollback's own execution detail; the change's own
coarser status becomes ``ROLLED_BACK`` the moment execution starts, not
when it finishes -- the same distinction Prompt 052 draws between an
incident's own status and its finer-grained SLA/escalation records.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.exceptions.conflict import ConflictError
from shared_core.logging.logger import get_logger

from app.changes.engine import validate_transition
from app.events.change_events import SOURCE_SERVICE, RollbackCompletedEvent, RollbackStartedEvent
from app.models.enums import ChangeStatus, RollbackStatus, change_status_of, rollback_status_of
from app.models.implementation import ChangeRollback
from app.notifications.change_notifications import ChangeNotificationService
from app.repositories.change import ChangeRequestRepository
from app.repositories.implementation import ChangeRollbackRepository
from app.types import EventPublisher

logger = get_logger("app.services.rollback")

_ROLLBACK_ELIGIBLE_STATUSES = frozenset({ChangeStatus.IN_PROGRESS, ChangeStatus.VALIDATION})


class RollbackService:
    """Rollback planning, approval, and execution."""

    def __init__(
        self,
        rollbacks: ChangeRollbackRepository,
        changes: ChangeRequestRepository,
        notifications: ChangeNotificationService,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._rollbacks = rollbacks
        self._changes = changes
        self._notifications = notifications
        self._publish = publish_event

    async def _publish_event(self, event: Any) -> None:
        if self._publish is not None:
            await self._publish(event)

    async def plan(
        self,
        organization_id: UUID,
        change_id: UUID,
        *,
        plan: str,
        triggered_reason: str,
        triggered_by: str | None = None,
    ) -> ChangeRollback:
        """Prepare a rollback plan, without executing it yet.

        Raises:
            ConflictError: If the change is not in a status a rollback
                could apply to.
        """
        stored = await self._changes.require_in_org(organization_id, change_id)
        current = change_status_of(stored.status)
        if current not in _ROLLBACK_ELIGIBLE_STATUSES:
            raise ConflictError(
                f"{stored.reference} is {current!s}; there is nothing to roll back."
            )
        return await self._rollbacks.create(
            ChangeRollback(
                organization_id=organization_id,
                change_id=change_id,
                status=RollbackStatus.PLANNED,
                plan=plan,
                triggered_by=triggered_by,
                triggered_reason=triggered_reason,
            )
        )

    async def approve(
        self, organization_id: UUID, rollback_id: UUID, *, approved_by: str
    ) -> ChangeRollback:
        """Approve a planned rollback.

        Raises:
            ConflictError: If it is not currently ``PLANNED``.
        """
        row = await self._rollbacks.require_in_org(organization_id, rollback_id)
        if rollback_status_of(row.status) is not RollbackStatus.PLANNED:
            raise ConflictError(f"Rollback {rollback_id} is {row.status!s}, not planned.")
        row.approved_by = approved_by
        row.approved_at = datetime.now(UTC)
        return await self._rollbacks.update(row)

    async def start(
        self, organization_id: UUID, rollback_id: UUID, *, actor_id: UUID | None = None
    ) -> ChangeRollback:
        """Begin executing an approved rollback, moving the change to ``ROLLED_BACK``.

        Raises:
            ConflictError: If it has not been approved yet, or the
                change has moved out of a rollback-eligible status since
                the plan was written.
        """
        moment = datetime.now(UTC)
        row = await self._rollbacks.require_in_org(organization_id, rollback_id)
        if row.approved_at is None:
            raise ConflictError(f"Rollback {rollback_id} has not been approved yet.")

        stored = await self._changes.require_in_org(organization_id, row.change_id)
        validate_transition(change_status_of(stored.status), ChangeStatus.ROLLED_BACK)

        row.status = RollbackStatus.IN_PROGRESS
        row.started_at = moment
        await self._rollbacks.update(row)

        stored.status = ChangeStatus.ROLLED_BACK
        stored.actual_end_at = moment
        if stored.actual_start_at is not None:
            stored.implementation_duration_seconds = (
                moment - stored.actual_start_at
            ).total_seconds()
        stored.updated_by = actor_id
        await self._changes.update(stored)

        if stored.technical_owner_id:
            await self._notifications.send_rollback_started(
                stored.technical_owner_id,
                reference=stored.reference,
                title=stored.title,
                reason=row.triggered_reason,
            )
        await self._publish_event(
            RollbackStartedEvent(
                source_service=SOURCE_SERVICE,
                payload={
                    "organization_id": str(organization_id),
                    "change_id": str(row.change_id),
                    "reason": row.triggered_reason,
                },
            )
        )
        return row

    async def complete(
        self, organization_id: UUID, rollback_id: UUID, *, validation_summary: str | None = None
    ) -> ChangeRollback:
        """Mark a rollback finished.

        Raises:
            ConflictError: If it is not currently ``IN_PROGRESS``.
        """
        row = await self._rollbacks.require_in_org(organization_id, rollback_id)
        if rollback_status_of(row.status) is not RollbackStatus.IN_PROGRESS:
            raise ConflictError(f"Rollback {rollback_id} is {row.status!s}, not in progress.")
        row.status = RollbackStatus.COMPLETED
        row.completed_at = datetime.now(UTC)
        row.validation_summary = validation_summary
        updated = await self._rollbacks.update(row)

        await self._publish_event(
            RollbackCompletedEvent(
                source_service=SOURCE_SERVICE,
                payload={
                    "organization_id": str(organization_id),
                    "change_id": str(row.change_id),
                    "status": "completed",
                },
            )
        )
        return updated

    async def fail(
        self, organization_id: UUID, rollback_id: UUID, *, reason: str
    ) -> ChangeRollback:
        """Mark a rollback attempt failed.

        The change stays ``ROLLED_BACK`` regardless -- even a failed
        rollback attempt means the change did not complete successfully,
        and a failed *rollback* is an operational emergency of its own,
        not a reason to leave the change looking like it succeeded.
        """
        row = await self._rollbacks.require_in_org(organization_id, rollback_id)
        row.status = RollbackStatus.FAILED
        row.validation_summary = reason
        return await self._rollbacks.update(row)

    async def list_for_change(self, organization_id: UUID, change_id: UUID) -> list[ChangeRollback]:
        """Every rollback attempt for one change."""
        return await self._rollbacks.list_for_change(organization_id, change_id)


__all__ = ["RollbackService"]
