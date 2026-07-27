"""Durable persistence of every SDK-emitted workflow runtime event. See
:class:`~app.models.workflow_event.WorkflowEventRecord`'s own docstring
for why this exists alongside the platform-wide event bus.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from app.models.workflow_event import WorkflowEventRecord
from app.repositories.workflow_event import WorkflowEventRecordRepository


class WorkflowEventService:
    """Records and reads a workflow instance's own durable event history."""

    def __init__(self, events: WorkflowEventRecordRepository) -> None:
        self._events = events

    async def record(
        self,
        *,
        organization_id: UUID,
        instance_id: UUID,
        event_type: str,
        payload: dict[str, Any],
        occurred_at: datetime,
    ) -> WorkflowEventRecord:
        """Durably record one SDK-emitted event for *instance_id*."""
        return await self._events.create(
            WorkflowEventRecord(
                organization_id=organization_id,
                instance_id=instance_id,
                event_type=event_type,
                payload=payload,
                occurred_at=occurred_at,
            )
        )

    async def list_for_instance(self, instance_id: UUID) -> list[WorkflowEventRecord]:
        """Every event recorded for *instance_id*, oldest first."""
        return await self._events.list_for_instance(instance_id)


__all__ = ["WorkflowEventService"]
