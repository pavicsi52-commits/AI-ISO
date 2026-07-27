"""Validation analytics computation. Per docs/043 "ANALYTICS"
"Collect": Execution Count, Pass Rate, Failure Rate, Validation
Duration, Top Failures, Trend Analysis, Asset Health Trends,
Compliance Trends. Computed on demand and cached, the same "cached,
not live" shape ``services/workflow-runtime-service``'s own
``WorkflowStatisticsService`` already established.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime
from uuid import UUID

from app.models.enums import ValidationExecutionStatus
from app.models.validation_statistics import ValidationStatistics
from app.repositories.validation_execution import ValidationExecutionRepository
from app.repositories.validation_failure import ValidationFailureRepository
from app.repositories.validation_history import ValidationHistoryRepository
from app.repositories.validation_profile import ValidationProfileRepository
from app.repositories.validation_statistics import ValidationStatisticsRepository

_TERMINAL_STATUSES = frozenset(
    {
        ValidationExecutionStatus.PASSED,
        ValidationExecutionStatus.FAILED,
        ValidationExecutionStatus.WARNING,
        ValidationExecutionStatus.CANCELLED,
        ValidationExecutionStatus.TIMEOUT,
    }
)
_PASSING_STATUSES = frozenset({ValidationExecutionStatus.PASSED, ValidationExecutionStatus.WARNING})


class ValidationStatisticsService:
    """Recomputes and reads an organization's cached validation analytics."""

    def __init__(
        self,
        statistics: ValidationStatisticsRepository,
        profiles: ValidationProfileRepository,
        executions: ValidationExecutionRepository,
        failures: ValidationFailureRepository,
        history: ValidationHistoryRepository,
    ) -> None:
        self._statistics = statistics
        self._profiles = profiles
        self._executions = executions
        self._failures = failures
        self._history = history

    async def get_for_org(self, organization_id: UUID) -> ValidationStatistics:
        """Return *organization_id*'s cached snapshot, recomputing if none exists yet."""
        existing = await self._statistics.get_for_org(organization_id)
        if existing is not None:
            return existing
        return await self.recompute(organization_id)

    async def recompute(self, organization_id: UUID) -> ValidationStatistics:
        """Recompute and persist *organization_id*'s statistics snapshot."""
        profiles = await self._profiles.list_for_org(organization_id)
        executions = await self._executions.list_for_org(organization_id)

        terminal = [e for e in executions if e.status in _TERMINAL_STATUSES]
        passing = sum(1 for e in terminal if e.status in _PASSING_STATUSES)
        durations = [
            (e.finished_at - e.started_at).total_seconds()
            for e in terminal
            if e.started_at is not None and e.finished_at is not None
        ]

        unresolved_failures = await self._failures.list_unresolved_for_org(organization_id)
        top_failures = Counter(str(failure.severity) for failure in unresolved_failures)

        trend_data: Counter[str] = Counter()
        for execution in executions:
            trend_data[execution.created_at.date().isoformat()] += 1

        asset_health_trends: dict[str, list[float]] = defaultdict(list)
        for record in await self._history.list_for_org(organization_id):
            asset_health_trends[str(record.target_id)].append(record.score or 0.0)

        snapshot_fields = {
            "total_profiles": len(profiles),
            "total_executions": len(executions),
            "pass_rate": passing / len(terminal) if terminal else 0.0,
            "failure_rate": (len(terminal) - passing) / len(terminal) if terminal else 0.0,
            "average_duration_seconds": sum(durations) / len(durations) if durations else 0.0,
            "top_failures": dict(top_failures),
            "trend_data": dict(trend_data),
            "asset_health_trends": dict(asset_health_trends),
            "compliance_trends": {},
            "computed_at": datetime.now(UTC),
        }

        existing = await self._statistics.get_for_org(organization_id)
        if existing is not None:
            for field, value in snapshot_fields.items():
                setattr(existing, field, value)
            return existing
        return await self._statistics.create(
            ValidationStatistics(organization_id=organization_id, **snapshot_fields)
        )


__all__ = ["ValidationStatisticsService"]
