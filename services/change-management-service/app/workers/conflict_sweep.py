"""The scheduling conflict sweep worker.

Re-runs conflict detection for every change still scheduled ahead, so a
change scheduled *after* another that conflicts with it gets caught even
though it was not the one whose own ``detect`` endpoint anyone called --
conflict detection is otherwise only triggered by the newer change's own
scheduling action, and never re-checked as the calendar around it shifts.

**Leader-elected** through ``shared_core.scheduler`` -- see
:mod:`app.workers.registrar`. **One session per organization**, so a
failure sweeping one tenant's changes does not poison the transaction
the next tenant's sweep needs.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from shared_core.logging.logger import get_logger
from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.change import ChangeRequest
from app.repositories.change import ChangeRequestRepository
from app.repositories.conflict import ChangeConflictRepository
from app.services.conflict import ConflictService

logger = get_logger("app.workers.conflict_sweep")


class ConflictSweepWorker:
    """Re-checks every organization's scheduled changes for new conflicts."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        max_per_tick: int = 500,
        slack_hours: int = 4,
    ) -> None:
        self._session_factory = session_factory
        self._max_per_tick = max_per_tick
        self._slack_hours = slack_hours

    async def run_job(self, _job: object) -> None:
        """Entry point matching ``shared_core.scheduler``'s own ``JobFn``."""
        await self.tick()

    async def tick(self) -> dict[str, int]:
        """Sweep every organization; returns aggregate change/conflict counts."""
        organizations = await self._organizations()
        changes_checked = conflicts_found = 0
        for organization_id in organizations:
            checked, found = await self._sweep(organization_id)
            changes_checked += checked
            conflicts_found += found
        logger.info(
            "Conflict sweep complete.",
            extra={
                "extra_fields": {
                    "organizations": len(organizations),
                    "changes_checked": changes_checked,
                    "conflicts_found": conflicts_found,
                }
            },
        )
        return {
            "organizations": len(organizations),
            "changes_checked": changes_checked,
            "conflicts_found": conflicts_found,
        }

    async def _organizations(self) -> list[UUID]:
        """Every organization with at least one change."""
        async with self._session_factory() as session:
            statement = select(distinct(ChangeRequest.organization_id)).limit(self._max_per_tick)
            result = await session.execute(statement)
            return [row for row in result.scalars().all() if row is not None]

    async def _sweep(self, organization_id: UUID) -> tuple[int, int]:
        """Sweep one organization's scheduled changes under its own session."""
        try:
            async with self._session_factory() as session:
                changes = ChangeRequestRepository(session)
                service = ConflictService(
                    ChangeConflictRepository(session), changes, slack_hours=self._slack_hours
                )
                now = datetime.now(UTC)
                scheduled = await changes.list_scheduled_between(
                    organization_id, start=now, end=now + timedelta(days=365)
                )
                found = 0
                for change in scheduled:
                    found += len(await service.detect_for_change(organization_id, change.id))
                await session.commit()
            return len(scheduled), found
        except Exception as exc:
            logger.warning(
                "A conflict sweep failed for one organization; the rest of the tick continues.",
                extra={
                    "extra_fields": {"organization_id": str(organization_id), "error": str(exc)}
                },
            )
            return 0, 0


__all__ = ["ConflictSweepWorker"]
