"""The announcement expiry sweep worker.

Expires every published announcement whose ``expires_at`` has passed
(docs/055 "ANNOUNCEMENTS": "Expiration Dates"). **Leader-elected**
through ``shared_core.scheduler`` -- see :mod:`app.workers.registrar`.
"""

from __future__ import annotations

from datetime import UTC, datetime

from shared_core.logging.logger import get_logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.repositories.announcement import NotificationAnnouncementRepository
from app.services.announcement import AnnouncementService

logger = get_logger("app.workers.announcement_expiry")


class AnnouncementExpiryWorker:
    """Expires every published announcement whose ``expires_at`` has passed."""

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], *, max_per_tick: int = 500
    ) -> None:
        self._session_factory = session_factory
        self._max_per_tick = max_per_tick

    async def run_job(self, _job: object) -> None:
        """Entry point matching ``shared_core.scheduler``'s own ``JobFn``."""
        await self.tick()

    async def tick(self) -> int:
        """Expire every due announcement; returns how many were expired."""
        try:
            async with self._session_factory() as session:
                service = AnnouncementService(NotificationAnnouncementRepository(session))
                expired = await service.expire_due(now=datetime.now(UTC), limit=self._max_per_tick)
                await session.commit()
            logger.info(
                "Announcement expiry sweep complete.", extra={"extra_fields": {"expired": expired}}
            )
            return expired
        except Exception as exc:
            logger.warning(
                "The announcement expiry sweep tick failed; the next tick will retry.",
                extra={"extra_fields": {"error": str(exc)}},
            )
            return 0


__all__ = ["AnnouncementExpiryWorker"]
