"""The approval expiry sweep worker.

Wraps :meth:`~app.services.approval.ApprovalService.sweep_expired`.
**Leader-elected** through ``shared_core.scheduler`` -- see
:mod:`app.workers.registrar`. **One session per organization**, so a
failure sweeping one tenant's approvals does not poison the transaction
the next tenant's sweep needs.
"""

from __future__ import annotations

from uuid import UUID

from shared_core.logging.logger import get_logger
from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.approval import ChangeApproval
from app.notifications.change_notifications import ChangeNotificationService
from app.repositories.approval import ChangeApprovalRepository
from app.repositories.change import ChangeRequestRepository
from app.services.approval import ApprovalService

logger = get_logger("app.workers.approval_expiry_sweep")


class ApprovalExpirySweepWorker:
    """Marks every overdue pending approval step expired, per organization."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        notifications: ChangeNotificationService,
        *,
        max_per_tick: int = 500,
        minimum_approvals_high_risk: int = 2,
    ) -> None:
        self._session_factory = session_factory
        self._notifications = notifications
        self._max_per_tick = max_per_tick
        self._minimum_approvals_high_risk = minimum_approvals_high_risk

    async def run_job(self, _job: object) -> None:
        """Entry point matching ``shared_core.scheduler``'s own ``JobFn``."""
        await self.tick()

    async def tick(self) -> int:
        """Sweep every organization; returns how many steps expired."""
        organizations = await self._organizations()
        expired = 0
        for organization_id in organizations:
            expired += await self._sweep(organization_id)
        logger.info(
            "Approval expiry sweep complete.",
            extra={"extra_fields": {"organizations": len(organizations), "expired": expired}},
        )
        return expired

    async def _organizations(self) -> list[UUID]:
        """Every organization with at least one approval step."""
        async with self._session_factory() as session:
            statement = select(distinct(ChangeApproval.organization_id)).limit(self._max_per_tick)
            result = await session.execute(statement)
            return [row for row in result.scalars().all() if row is not None]

    async def _sweep(self, organization_id: UUID) -> int:
        """Sweep one organization's approval steps under its own session."""
        try:
            async with self._session_factory() as session:
                service = ApprovalService(
                    ChangeApprovalRepository(session),
                    ChangeRequestRepository(session),
                    self._notifications,
                    minimum_approvals_high_risk=self._minimum_approvals_high_risk,
                )
                expired = await service.sweep_expired(organization_id)
                await session.commit()
            return expired
        except Exception as exc:
            logger.warning(
                "An approval expiry sweep failed for one organization; "
                "the rest of the tick continues.",
                extra={
                    "extra_fields": {"organization_id": str(organization_id), "error": str(exc)}
                },
            )
            return 0


__all__ = ["ApprovalExpirySweepWorker"]
