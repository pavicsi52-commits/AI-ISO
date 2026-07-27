"""Workflow runtime analytics computation. Per docs/042 "ANALYTICS"
"Collect": Workflow Count, Execution Time, Failure Rate, Success Rate,
Average Duration, Checkpoint Count, Approval Count, Replay Count,
Rollback Count, Node Statistics, Execution Trends. Computed on demand
and cached, the same "cached, not live" shape
``services/playbook-service``'s own ``PlaybookStatisticsService``
established.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from uuid import UUID

from app.models.enums import WorkflowInstanceStatus
from app.models.workflow_statistics import WorkflowStatistics
from app.repositories.workflow_approval import WorkflowApprovalRepository
from app.repositories.workflow_checkpoint import WorkflowCheckpointRepository
from app.repositories.workflow_definition import WorkflowDefinitionRepository
from app.repositories.workflow_execution_step import WorkflowExecutionStepRepository
from app.repositories.workflow_instance import WorkflowInstanceRepository
from app.repositories.workflow_replay import WorkflowReplayRepository
from app.repositories.workflow_statistics import WorkflowStatisticsRepository

_TERMINAL_STATUSES = frozenset(
    {
        WorkflowInstanceStatus.COMPLETED,
        WorkflowInstanceStatus.FAILED,
        WorkflowInstanceStatus.CANCELLED,
        WorkflowInstanceStatus.ROLLED_BACK,
    }
)


class WorkflowStatisticsService:
    """Recomputes and reads an organization's cached workflow-runtime analytics."""

    def __init__(
        self,
        statistics: WorkflowStatisticsRepository,
        definitions: WorkflowDefinitionRepository,
        instances: WorkflowInstanceRepository,
        steps: WorkflowExecutionStepRepository,
        approvals: WorkflowApprovalRepository,
        checkpoints: WorkflowCheckpointRepository,
        replays: WorkflowReplayRepository,
    ) -> None:
        self._statistics = statistics
        self._definitions = definitions
        self._instances = instances
        self._steps = steps
        self._approvals = approvals
        self._checkpoints = checkpoints
        self._replays = replays

    async def get_for_org(self, organization_id: UUID) -> WorkflowStatistics:
        """Return *organization_id*'s cached snapshot, recomputing if none exists yet."""
        existing = await self._statistics.get_for_org(organization_id)
        if existing is not None:
            return existing
        return await self.recompute(organization_id)

    async def recompute(self, organization_id: UUID) -> WorkflowStatistics:
        """Recompute and persist *organization_id*'s statistics snapshot."""
        definitions = await self._definitions.list_for_org(organization_id)
        instances = await self._instances.list_for_org(organization_id)

        terminal = [instance for instance in instances if instance.status in _TERMINAL_STATUSES]
        succeeded = sum(1 for i in terminal if i.status == WorkflowInstanceStatus.COMPLETED)
        rolled_back = sum(1 for i in terminal if i.status == WorkflowInstanceStatus.ROLLED_BACK)
        durations = [
            (i.finished_at - i.started_at).total_seconds()
            for i in terminal
            if i.started_at is not None and i.finished_at is not None
        ]

        node_statistics: Counter[str] = Counter()
        checkpoint_count = 0
        for instance in instances:
            for step in await self._steps.list_for_instance(instance.id):
                node_statistics[str(step.node_type)] += 1
            checkpoint_count += len(await self._checkpoints.list_for_instance(instance.id))

        approval_count = 0
        replay_count = 0
        for instance in instances:
            approval_count += len(await self._approvals.list_for_instance(instance.id))
            replay_count += len(await self._replays.list_for_instance(instance.id))

        execution_trends: Counter[str] = Counter()
        for instance in instances:
            execution_trends[instance.created_at.date().isoformat()] += 1

        snapshot_fields = {
            "total_workflows": len(definitions),
            "total_executions": len(instances),
            "success_rate": succeeded / len(terminal) if terminal else 0.0,
            "failure_rate": (len(terminal) - succeeded) / len(terminal) if terminal else 0.0,
            "average_duration_seconds": sum(durations) / len(durations) if durations else 0.0,
            "checkpoint_count": checkpoint_count,
            "approval_count": approval_count,
            "replay_count": replay_count,
            "rollback_count": rolled_back,
            "node_statistics": dict(node_statistics),
            "execution_trends": dict(execution_trends),
            "computed_at": datetime.now(UTC),
        }

        existing = await self._statistics.get_for_org(organization_id)
        if existing is not None:
            for field, value in snapshot_fields.items():
                setattr(existing, field, value)
            return existing
        return await self._statistics.create(
            WorkflowStatistics(organization_id=organization_id, **snapshot_fields)
        )


__all__ = ["WorkflowStatisticsService"]
