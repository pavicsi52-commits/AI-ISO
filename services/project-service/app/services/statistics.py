"""Project analytics/statistics computation.

Per docs/034 "PROJECT ANALYTICS": Member Count, Automation Count,
Workflow Count, Validation Count, Inventory Count, Connector Count, AI
Usage, Storage Usage, Execution Statistics, Failure Rates, Success
Rates. See ``app/models/project_statistics.py``'s docstring for why
only ``member_count`` is computed from real data this service owns.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.models.project_statistics import ProjectStatistics
from app.repositories.project_member import ProjectMemberRepository
from app.repositories.project_statistics import ProjectStatisticsRepository


class ProjectStatisticsService:
    """Recomputes and reads a project's usage snapshot."""

    def __init__(
        self, statistics: ProjectStatisticsRepository, members: ProjectMemberRepository
    ) -> None:
        self._statistics = statistics
        self._members = members

    async def recompute(self, project_id: UUID, *, organization_id: UUID) -> ProjectStatistics:
        """Recompute and persist *project_id*'s usage snapshot ("Collect ...")."""
        member_count = await self._members.count_for_project(project_id)
        now = datetime.now(UTC)

        existing = await self._statistics.get_for_project(project_id)
        if existing is not None:
            existing.member_count = member_count
            existing.computed_at = now
            return existing
        return await self._statistics.create(
            ProjectStatistics(
                project_id=project_id,
                organization_id=organization_id,
                member_count=member_count,
                computed_at=now,
            )
        )

    async def get_or_recompute(
        self, project_id: UUID, *, organization_id: UUID
    ) -> ProjectStatistics:
        """Return the last-computed snapshot, computing it for the first time if missing."""
        existing = await self._statistics.get_for_project(project_id)
        if existing is not None:
            return existing
        return await self.recompute(project_id, organization_id=organization_id)


__all__ = ["ProjectStatisticsService"]
