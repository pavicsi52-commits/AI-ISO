"""Automation analytics computation. Per docs/040 "ANALYTICS" "Collect":
Execution Count, Success Rate, Failure Rate, Average Runtime, Resource
Usage, Connector Usage, Automation Trends, Top Failed Jobs, Most
Executed Jobs, Execution Heatmaps. Recomputed periodically rather than
aggregated live on every request, the same "cached, not live" shape
``services/configuration-management-service``'s own
``ConfigurationStatisticsService`` established.

**Resource Usage**: no CPU/memory/disk metrics are captured anywhere
in this service's own data model (steps record only exit code and
duration) -- :attr:`~app.models.automation_statistics.AutomationStatistics
.resource_usage` is honestly left an empty mapping rather than
fabricated, until a metrics source is wired in.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from uuid import UUID

from app.models.automation_execution import AutomationExecution
from app.models.automation_statistics import AutomationStatistics
from app.models.enums import ExecutionStatus
from app.repositories.automation_execution import AutomationExecutionRepository
from app.repositories.automation_execution_step import AutomationExecutionStepRepository
from app.repositories.automation_job import AutomationJobRepository
from app.repositories.automation_statistics import AutomationStatisticsRepository
from app.repositories.automation_target import AutomationTargetRepository

_TOP_N = 5


class AutomationStatisticsService:
    """Recomputes and reads an organization's cached automation analytics."""

    def __init__(
        self,
        statistics: AutomationStatisticsRepository,
        jobs: AutomationJobRepository,
        executions: AutomationExecutionRepository,
        steps: AutomationExecutionStepRepository,
        targets: AutomationTargetRepository,
    ) -> None:
        self._statistics = statistics
        self._jobs = jobs
        self._executions = executions
        self._steps = steps
        self._targets = targets

    async def get_for_org(self, organization_id: UUID) -> AutomationStatistics:
        """Return *organization_id*'s cached snapshot, recomputing if none exists yet."""
        existing = await self._statistics.get_for_org(organization_id)
        if existing is not None:
            return existing
        return await self.recompute(organization_id)

    async def recompute(self, organization_id: UUID) -> AutomationStatistics:
        """Recompute and persist *organization_id*'s statistics snapshot."""
        jobs = await self._jobs.list_for_org(organization_id)
        executions = await self._executions.list_for_org(organization_id)

        total_executions = len(executions)
        completed = sum(1 for e in executions if e.status == ExecutionStatus.COMPLETED)
        failed = sum(1 for e in executions if e.status == ExecutionStatus.FAILED)
        success_rate = completed / total_executions if total_executions else 0.0
        failure_rate = failed / total_executions if total_executions else 0.0

        durations = [
            (e.completed_at - e.started_at).total_seconds()
            for e in executions
            if e.started_at is not None and e.completed_at is not None
        ]
        average_runtime_seconds = sum(durations) / len(durations) if durations else 0.0

        connector_usage = await self._compute_connector_usage(executions)

        executions_per_job: Counter[str] = Counter(str(e.job_id) for e in executions)
        failures_per_job: Counter[str] = Counter(
            str(e.job_id) for e in executions if e.status == ExecutionStatus.FAILED
        )
        job_names = {str(job.id): job.name for job in jobs}
        most_executed_jobs = {
            job_names.get(job_id, job_id): count
            for job_id, count in executions_per_job.most_common(_TOP_N)
        }
        top_failed_jobs = {
            job_names.get(job_id, job_id): count
            for job_id, count in failures_per_job.most_common(_TOP_N)
        }

        execution_heatmap = dict(
            Counter(e.created_at.date().isoformat() for e in executions if e.created_at is not None)
        )

        snapshot_fields = {
            "total_jobs": len(jobs),
            "total_executions": total_executions,
            "success_rate": success_rate,
            "failure_rate": failure_rate,
            "average_runtime_seconds": average_runtime_seconds,
            "resource_usage": {},
            "connector_usage": connector_usage,
            "top_failed_jobs": top_failed_jobs,
            "most_executed_jobs": most_executed_jobs,
            "execution_heatmap": execution_heatmap,
            "computed_at": datetime.now(UTC),
        }

        existing = await self._statistics.get_for_org(organization_id)
        if existing is not None:
            for field, value in snapshot_fields.items():
                setattr(existing, field, value)
            return existing
        return await self._statistics.create(
            AutomationStatistics(organization_id=organization_id, **snapshot_fields)
        )

    async def _compute_connector_usage(
        self, executions: list[AutomationExecution]
    ) -> dict[str, int]:
        target_ids: set[UUID] = set()
        target_id_occurrences: list[UUID] = []
        for execution in executions:
            for step in await self._steps.list_for_execution(execution.id):
                if step.target_id is not None:
                    target_ids.add(step.target_id)
                    target_id_occurrences.append(step.target_id)

        if not target_ids:
            return {}
        targets = await self._targets.list_by_ids(list(target_ids))
        connector_by_target = {target.id: str(target.connector_type) for target in targets}
        usage: Counter[str] = Counter(
            connector_by_target[target_id]
            for target_id in target_id_occurrences
            if target_id in connector_by_target
        )
        return dict(usage)


__all__ = ["AutomationStatisticsService"]
