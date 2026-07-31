"""The statistics rollup worker.

Recomputes every organization's statistics window from the assessments,
findings, risks, exceptions, and remediations that already exist.

**Leader-elected** through ``shared_core.scheduler`` -- see
:mod:`app.workers.registrar`.

**One session per organization.** A failure on one tenant must not poison
the transaction the next one needs -- and in a service whose whole
purpose is to report accurately, a tenant silently missing from a
rollup is worse than a rollup that visibly failed.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from shared_core.logging.logger import get_logger
from shared_core.scheduler import Job
from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.framework import ComplianceFramework
from app.repositories.catalogue import ControlRepository, FrameworkRepository
from app.repositories.governance import (
    ExceptionRepository,
    FindingRepository,
    RemediationRepository,
    RiskRepository,
    ScoreRepository,
    StatisticRepository,
)
from app.repositories.runs import (
    AssessmentRepository,
    EvidenceRepository,
    ResultRepository,
    ScanRepository,
)
from app.services.reporting import StatisticsService

logger = get_logger("app.workers.statistics")


class StatisticsWorker:
    """Recomputes every organization's compliance statistics."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        max_per_tick: int = 200,
        window_hours: int = 24,
    ) -> None:
        self._session_factory = session_factory
        self._max_per_tick = max_per_tick
        self._window_hours = window_hours

    async def run_job(self, _job: Job) -> None:
        """Entry point matching ``shared_core.scheduler``'s own ``JobFn``.

        The framework calls a job with the :class:`Job` itself and expects
        nothing back, while :meth:`tick` returns a count for direct
        testing. This adapter keeps both honest instead of bending one to
        fit the other -- and its existence is why a signature mismatch
        cannot reach production as "the scheduler silently never fired".
        """
        await self.tick()

    async def tick(self) -> int:
        """Recompute every organization's window; returns how many succeeded."""
        organizations = await self._organizations()
        done = 0
        for organization_id in organizations:
            if await self._recompute(organization_id):
                done += 1
        logger.info(
            "Compliance statistics rollup complete.",
            extra={"extra_fields": {"organizations": len(organizations), "succeeded": done}},
        )
        return done

    async def _organizations(self) -> list[UUID]:
        """Every organization with a compliance catalogue.

        Derived from ``compliance_frameworks`` rather than from
        assessments: an organization that has installed frameworks but
        not yet run anything still wants a window -- one whose numbers
        are all zero is a true and useful statement, and its absence
        would look identical to a broken rollup.
        """
        async with self._session_factory() as session:
            statement = (
                select(distinct(ComplianceFramework.organization_id))
                .where(ComplianceFramework.deleted_at.is_(None))
                .limit(self._max_per_tick)
            )
            result = await session.execute(statement)
            return [row for row in result.scalars().all() if row is not None]

    async def _recompute(self, organization_id: UUID) -> bool:
        """Recompute one organization's window under its own session."""
        try:
            now = datetime.now(UTC)
            async with self._session_factory() as session:
                service = StatisticsService(
                    StatisticRepository(session),
                    AssessmentRepository(session),
                    ScanRepository(session),
                    ResultRepository(session),
                    EvidenceRepository(session),
                    FindingRepository(session),
                    RiskRepository(session),
                    ExceptionRepository(session),
                    RemediationRepository(session),
                    ScoreRepository(session),
                    ControlRepository(session),
                    FrameworkRepository(session),
                )
                await service.rollup(
                    organization_id,
                    window_start=now - timedelta(hours=self._window_hours),
                    window_end=now,
                )
                await session.commit()
            return True
        except Exception as exc:
            logger.warning(
                "A compliance statistics rollup failed; the rest of the tick continues.",
                extra={
                    "extra_fields": {
                        "organization_id": str(organization_id),
                        "error": str(exc),
                    }
                },
            )
            return False


__all__ = ["StatisticsWorker"]
