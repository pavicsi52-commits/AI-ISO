"""State transition history. Per docs/042 "AUDIT" "State Changes"."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.models.enums import WorkflowInstanceStatus
from app.models.workflow_state import WorkflowStateTransition
from app.repositories.workflow_state import WorkflowStateTransitionRepository


class WorkflowStateTransitionService:
    """Records and reads a workflow instance's own state transition history."""

    def __init__(self, states: WorkflowStateTransitionRepository) -> None:
        self._states = states

    async def record(
        self,
        *,
        organization_id: UUID,
        instance_id: UUID,
        from_status: WorkflowInstanceStatus | None,
        to_status: WorkflowInstanceStatus,
    ) -> WorkflowStateTransition:
        """Record one state transition for *instance_id*."""
        return await self._states.create(
            WorkflowStateTransition(
                organization_id=organization_id,
                instance_id=instance_id,
                from_status=from_status,
                to_status=to_status,
                transitioned_at=datetime.now(UTC),
            )
        )

    async def list_for_instance(self, instance_id: UUID) -> list[WorkflowStateTransition]:
        """Every state transition recorded for *instance_id*, oldest first."""
        return await self._states.list_for_instance(instance_id)


__all__ = ["WorkflowStateTransitionService"]
