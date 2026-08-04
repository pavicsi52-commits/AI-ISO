"""The maintenance sweep worker.

Reminds a change's owner when a post-implementation review is overdue --
the single most common way a lessons-learned process quietly stops
producing any lessons, the same reasoning Prompt 052 applies to a
missing postmortem.

**Leader-elected** through ``shared_core.scheduler`` -- see
:mod:`app.workers.registrar`. **One session per organization**, so a
failure on one tenant does not poison the transaction the next one
needs.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from shared_core.logging.logger import get_logger
from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.change import ChangeRequest
from app.models.enums import ChangeStatus
from app.notifications.change_notifications import ChangeNotificationService
from app.repositories.change import ChangeRequestRepository
from app.repositories.pir import ChangePostReviewRepository

logger = get_logger("app.workers.maintenance")

_REVIEWABLE_STATUSES = (ChangeStatus.COMPLETED, ChangeStatus.ROLLED_BACK)


class MaintenanceWorker:
    """Reminds change owners that no post-implementation review exists yet."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        notifications: ChangeNotificationService,
        *,
        max_per_tick: int = 200,
        pir_due_days: int = 5,
    ) -> None:
        self._session_factory = session_factory
        self._notifications = notifications
        self._max_per_tick = max_per_tick
        self._pir_due_days = pir_due_days

    async def run_job(self, _job: object) -> None:
        """Entry point matching ``shared_core.scheduler``'s own ``JobFn``."""
        await self.tick()

    async def tick(self) -> int:
        """Sweep every organization; returns how many reminders were sent."""
        organizations = await self._organizations()
        reminded = 0
        for organization_id in organizations:
            reminded += await self._sweep(organization_id)
        logger.info(
            "Change maintenance sweep complete.",
            extra={"extra_fields": {"organizations": len(organizations), "reminded": reminded}},
        )
        return reminded

    async def _organizations(self) -> list[UUID]:
        """Every organization with at least one change."""
        async with self._session_factory() as session:
            statement = select(distinct(ChangeRequest.organization_id)).limit(self._max_per_tick)
            result = await session.execute(statement)
            return [row for row in result.scalars().all() if row is not None]

    async def _sweep(self, organization_id: UUID) -> int:
        """Sweep one organization under its own session."""
        try:
            now = datetime.now(UTC)
            async with self._session_factory() as session:
                changes = ChangeRequestRepository(session)
                reviews = ChangePostReviewRepository(session)
                reminded = 0
                for status in _REVIEWABLE_STATUSES:
                    for change in await changes.list_filtered(
                        organization_id, status=status, limit=self._max_per_tick
                    ):
                        reminded += await self._remind_if_due(
                            organization_id, change, reviews, now=now
                        )
            return reminded
        except Exception as exc:
            logger.warning(
                "A change maintenance sweep failed for one organization; "
                "the rest of the tick continues.",
                extra={
                    "extra_fields": {"organization_id": str(organization_id), "error": str(exc)}
                },
            )
            return 0

    async def _remind_if_due(
        self,
        organization_id: UUID,
        change: ChangeRequest,
        reviews: ChangePostReviewRepository,
        *,
        now: datetime,
    ) -> int:
        finished_at = change.actual_end_at or change.completed_at
        if finished_at is None:
            return 0
        finished_days_ago = (now - finished_at).days
        if finished_days_ago < self._pir_due_days:
            return 0
        if not change.technical_owner_id:
            return 0
        if await reviews.get_for_change(organization_id, change.id) is not None:
            return 0
        await self._notifications.send_pir_due(
            change.technical_owner_id,
            reference=change.reference,
            title=change.title,
            completed_days_ago=finished_days_ago,
        )
        return 1


__all__ = ["MaintenanceWorker"]
