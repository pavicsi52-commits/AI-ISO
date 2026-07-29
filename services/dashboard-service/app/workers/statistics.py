"""The analytics rollup worker ("ANALYTICS").

Recomputes every organization's
:class:`~app.models.dashboard_statistics.DashboardStatistics` row from
the view, widget, and share rows that already exist.

**This one *is* leader-elected**, unlike
:mod:`app.workers.refresh`. The rollup is a pure database write with no
per-replica state, so N replicas computing it would be N times the load
for an identical result -- and two concurrent recomputes of the same
organization would race on the same row. Election is handled by
``shared_core.scheduler``; see :mod:`app.workers.registrar`.

**One session per organization.** A failure on one tenant must not
poison the transaction the next one needs.
"""

from __future__ import annotations

from uuid import UUID

from shared_core.logging.logger import get_logger
from shared_core.scheduler import Job
from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.dashboard import Dashboard
from app.repositories.dashboard import DashboardRepository
from app.repositories.dashboard_share import DashboardShareRepository
from app.repositories.dashboard_statistics import DashboardStatisticsRepository
from app.repositories.dashboard_view import DashboardViewRepository
from app.repositories.dashboard_widget import DashboardWidgetRepository
from app.services.statistics import StatisticsService

logger = get_logger("app.workers.statistics")


class StatisticsWorker:
    """Recomputes every organization's dashboard analytics."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        window_days: int = 30,
        max_per_tick: int = 200,
    ) -> None:
        self._session_factory = session_factory
        self._window_days = window_days
        self._max_per_tick = max_per_tick

    async def run_job(self, _job: Job) -> None:
        """Entry point matching ``shared_core.scheduler``'s own ``JobFn``.

        The framework calls a job with the :class:`Job` itself and
        expects nothing back, while :meth:`tick` returns a count for
        direct testing. This adapter keeps both honest instead of
        bending one to fit the other -- and its existence is why a
        signature mismatch cannot reach production as "the scheduler
        silently never fired".
        """
        await self.tick()

    async def tick(self) -> int:
        """Recompute every organization's rollup; returns how many succeeded."""
        organizations = await self._organizations()
        done = 0
        for organization_id in organizations:
            if await self._recompute(organization_id):
                done += 1
        logger.info(
            "Dashboard analytics rollup complete.",
            extra={"extra_fields": {"organizations": len(organizations), "succeeded": done}},
        )
        return done

    async def _organizations(self) -> list[UUID]:
        """Every organization that owns at least one dashboard.

        Derived in SQL rather than by loading dashboards: an
        installation with fifty thousand dashboards should still produce
        a short list of tenants.
        """
        async with self._session_factory() as session:
            statement = (
                select(distinct(Dashboard.organization_id))
                .where(Dashboard.deleted_at.is_(None))
                .limit(self._max_per_tick)
            )
            result = await session.execute(statement)
            return [row for row in result.scalars().all() if row is not None]

    async def _recompute(self, organization_id: UUID) -> bool:
        """Recompute one organization's rollup under its own session."""
        try:
            async with self._session_factory() as session:
                service = StatisticsService(
                    DashboardRepository(session),
                    DashboardWidgetRepository(session),
                    DashboardViewRepository(session),
                    DashboardShareRepository(session),
                    DashboardStatisticsRepository(session),
                )
                await service.refresh(organization_id, window_days=self._window_days)
                await session.commit()
            return True
        except Exception as exc:
            logger.warning(
                "An analytics rollup failed; the rest of the tick continues.",
                extra={
                    "extra_fields": {
                        "organization_id": str(organization_id),
                        "error": str(exc),
                    }
                },
            )
            return False


__all__ = ["StatisticsWorker"]
