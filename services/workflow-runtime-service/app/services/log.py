"""Structured log lines for a workflow instance, backing
``GET /workflow-instances/{id}/logs``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.models.workflow_log import WorkflowLog
from app.repositories.workflow_log import WorkflowLogRepository


class WorkflowLogService:
    """Records and reads workflow instance log lines."""

    def __init__(self, logs: WorkflowLogRepository) -> None:
        self._logs = logs

    async def record(
        self,
        *,
        organization_id: UUID,
        instance_id: UUID,
        message: str,
        level: str = "info",
        node_id: str | None = None,
    ) -> WorkflowLog:
        """Record one structured log line for *instance_id*."""
        return await self._logs.create(
            WorkflowLog(
                organization_id=organization_id,
                instance_id=instance_id,
                node_id=node_id,
                level=level,
                message=message,
                logged_at=datetime.now(UTC),
            )
        )

    async def list_for_instance(self, instance_id: UUID) -> list[WorkflowLog]:
        """Every log line recorded for *instance_id*, oldest first."""
        return await self._logs.list_for_instance(instance_id)


__all__ = ["WorkflowLogService"]
