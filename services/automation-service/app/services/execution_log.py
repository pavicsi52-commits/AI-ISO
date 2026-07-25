"""Structured execution log lines. Per docs/040 "LOGGING" "Capture":
Execution Logs, Console Output, Structured Logs, Connector Logs,
Timing, Errors, Warnings, Execution Metadata. Actual log rows are
written by :class:`~app.services.execution.AutomationExecutionService`
as it dispatches each step; this service only reads them back
("GET /automation/executions/{id}/logs").
"""

from __future__ import annotations

from uuid import UUID

from app.models.automation_execution_log import AutomationExecutionLog
from app.repositories.automation_execution_log import AutomationExecutionLogRepository


class AutomationExecutionLogService:
    """Reads structured log lines captured during automation executions."""

    def __init__(self, logs: AutomationExecutionLogRepository) -> None:
        self._logs = logs

    async def list_for_execution(self, execution_id: UUID) -> list[AutomationExecutionLog]:
        """Every log line recorded for *execution_id*, oldest first."""
        return await self._logs.list_for_execution(execution_id)


__all__ = ["AutomationExecutionLogService"]
