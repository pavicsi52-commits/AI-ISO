"""The statistics rollup worker.

Recomputes every organization's rolling traffic-statistics window from
the request/response logs that already exist. **Leader-elected** through
``shared_core.scheduler`` -- see :mod:`app.workers.registrar`.

**One session per organization.** A failure on one tenant must not
poison the transaction the next one needs, and a tenant silently missing
from a rollup is worse than a rollup that visibly failed for it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from shared_core.logging.logger import get_logger
from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.request import ApiRequestLog
from app.repositories.governance import ApiStatisticRepository
from app.repositories.request import ApiRequestLogRepository, ApiResponseLogRepository
from app.services.reporting import StatisticsService

logger = get_logger("app.workers.statistics_rollup")


class StatisticsRollupWorker:
    """Recomputes every organization's gateway traffic statistics."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        window_seconds: int,
        max_organizations_per_tick: int = 200,
    ) -> None:
        self._session_factory = session_factory
        self._window_seconds = window_seconds
        self._max_organizations_per_tick = max_organizations_per_tick

    async def run_job(self, _job: object) -> None:
        """Entry point matching ``shared_core.scheduler``'s own ``JobFn``."""
        await self.tick()

    async def tick(self) -> int:
        """Recompute every organization's window; returns how many succeeded."""
        organizations = await self._organizations()
        done = 0
        for organization_id in organizations:
            if await self._recompute(organization_id):
                done += 1
        logger.info(
            "Gateway statistics rollup complete.",
            extra={"extra_fields": {"organizations": len(organizations), "succeeded": done}},
        )
        return done

    async def _organizations(self) -> list[UUID]:
        """Every organization with at least one logged request."""
        async with self._session_factory() as session:
            statement = select(distinct(ApiRequestLog.organization_id)).limit(
                self._max_organizations_per_tick
            )
            result = await session.execute(statement)
            return [row for row in result.scalars().all() if row is not None]

    async def _recompute(self, organization_id: UUID) -> bool:
        """Recompute one organization's window under its own session."""
        try:
            now = datetime.now(UTC)
            async with self._session_factory() as session:
                service = StatisticsService(
                    ApiStatisticRepository(session),
                    ApiRequestLogRepository(session),
                    ApiResponseLogRepository(session),
                )
                await service.rollup(
                    organization_id,
                    window_start=now - timedelta(seconds=self._window_seconds),
                    window_end=now,
                )
                await session.commit()
            return True
        except Exception as exc:
            logger.warning(
                "A gateway statistics rollup failed; the rest of the tick continues.",
                extra={
                    "extra_fields": {"organization_id": str(organization_id), "error": str(exc)}
                },
            )
            return False


__all__ = ["StatisticsRollupWorker"]
