"""The analytics rollup worker.

Recomputes every organization's
:class:`~app.models.operations.PolicyStatistics` row from the decisions,
violations, and approvals that already exist.

**Leader-elected** through ``shared_core.scheduler`` -- see
:mod:`app.workers.registrar`.

**One session per organization.** A failure on one tenant must not poison
the transaction the next one needs.
"""

from __future__ import annotations

from uuid import UUID

from shared_core.logging.logger import get_logger
from shared_core.scheduler import Job
from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.policy import Policy
from app.repositories.policy import PolicyRepository
from app.repositories.runtime import (
    PolicyApprovalRepository,
    PolicyDecisionRepository,
    PolicyStatisticsRepository,
    PolicyViolationRepository,
)
from app.services.statistics import StatisticsService

logger = get_logger("app.workers.statistics")


class StatisticsWorker:
    """Recomputes every organization's policy analytics."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        max_per_tick: int = 200,
    ) -> None:
        self._session_factory = session_factory
        self._max_per_tick = max_per_tick

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
        """Recompute every organization's rollup; returns how many succeeded."""
        organizations = await self._organizations()
        done = 0
        for organization_id in organizations:
            if await self._recompute(organization_id):
                done += 1
        logger.info(
            "Policy analytics rollup complete.",
            extra={
                "extra_fields": {
                    "organizations": len(organizations),
                    "succeeded": done,
                }
            },
        )
        return done

    async def _organizations(self) -> list[UUID]:
        """Every organization with a policy catalogue.

        Derived from ``policies`` rather than from the decision log: an
        organization that has authored governance but not yet exercised
        it still wants a rollup, and one that has decisions but no
        policies is not a state this service can produce.
        """
        async with self._session_factory() as session:
            statement = (
                select(distinct(Policy.organization_id))
                .where(Policy.deleted_at.is_(None))
                .limit(self._max_per_tick)
            )
            result = await session.execute(statement)
            return [row for row in result.scalars().all() if row is not None]

    async def _recompute(self, organization_id: UUID) -> bool:
        """Recompute one organization's rollup under its own session."""
        try:
            async with self._session_factory() as session:
                service = StatisticsService(
                    PolicyRepository(session),
                    PolicyDecisionRepository(session),
                    PolicyViolationRepository(session),
                    PolicyApprovalRepository(session),
                    PolicyStatisticsRepository(session),
                )
                await service.refresh(organization_id)
                await session.commit()
            return True
        except Exception as exc:
            logger.warning(
                "A policy analytics rollup failed; the rest of the tick continues.",
                extra={
                    "extra_fields": {
                        "organization_id": str(organization_id),
                        "error": str(exc),
                    }
                },
            )
            return False


__all__ = ["StatisticsWorker"]
