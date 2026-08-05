"""The quota reset sweep worker.

Resets every quota whose tracked period has already ended, across every
organization, in one tick -- a thin wrapper over
:meth:`~app.services.quota.QuotaService.reset_due`, which already walks
every organization unscoped. **Leader-elected** through
``shared_core.scheduler`` -- see :mod:`app.workers.registrar`.
"""

from __future__ import annotations

from datetime import UTC, datetime

from shared_core.logging.logger import get_logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.repositories.quota import ApiQuotaPolicyRepository
from app.services.quota import QuotaService

logger = get_logger("app.workers.quota_reset_sweep")


class QuotaResetSweepWorker:
    """Resets every quota whose period has ended."""

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], *, max_per_tick: int = 500
    ) -> None:
        self._session_factory = session_factory
        self._max_per_tick = max_per_tick

    async def run_job(self, _job: object) -> None:
        """Entry point matching ``shared_core.scheduler``'s own ``JobFn``."""
        await self.tick()

    async def tick(self) -> int:
        """Reset every due quota; returns how many were reset."""
        try:
            async with self._session_factory() as session:
                service = QuotaService(ApiQuotaPolicyRepository(session))
                reset_count = await service.reset_due(now=datetime.now(UTC), limit=self._max_per_tick)
                await session.commit()
        except Exception as exc:
            logger.warning(
                "The quota reset sweep failed.", extra={"extra_fields": {"error": str(exc)}}
            )
            return 0
        logger.info("Quota reset sweep complete.", extra={"extra_fields": {"reset": reset_count}})
        return reset_count


__all__ = ["QuotaResetSweepWorker"]
