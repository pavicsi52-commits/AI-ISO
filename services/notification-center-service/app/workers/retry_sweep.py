"""The retry sweep worker.

Dispatches the next attempt for every unresolved retry-queue entry
whose ``next_retry_at`` has arrived. **Leader-elected** through
``shared_core.scheduler`` -- see :mod:`app.workers.registrar`.

Unlike a per-organization sweep, :meth:`~app.services.delivery
.DeliveryService.retry_due` already walks every organization's due
retries in one unscoped query (the retry queue has no natural per-tenant
partition worth a separate session each) -- so a single failure inside
one tick logs and skips the rest of *that* tick rather than aborting it
outright, and the next tick simply picks up whatever is still due.
"""

from __future__ import annotations

from datetime import UTC, datetime

from shared_core.logging.logger import get_logger
from shared_core.notifications.manager import NotificationManager
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config.settings import NotificationServiceSettings
from app.services.delivery import build_delivery_service
from app.types import EventPublisher

logger = get_logger("app.workers.retry_sweep")


class RetrySweepWorker:
    """Dispatches every retry-queue entry whose delay has elapsed."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        notification_manager: NotificationManager,
        settings: NotificationServiceSettings,
        *,
        publish_event: EventPublisher | None = None,
        max_per_tick: int = 500,
    ) -> None:
        self._session_factory = session_factory
        self._notification_manager = notification_manager
        self._settings = settings
        self._publish_event = publish_event
        self._max_per_tick = max_per_tick

    async def run_job(self, _job: object) -> None:
        """Entry point matching ``shared_core.scheduler``'s own ``JobFn``."""
        await self.tick()

    async def tick(self) -> int:
        """Attempt every due retry; returns how many were dispatched."""
        try:
            async with self._session_factory() as session:
                service = build_delivery_service(
                    session,
                    self._notification_manager,
                    self._settings,
                    publish_event=self._publish_event,
                )
                dispatched = await service.retry_due(
                    now=datetime.now(UTC), limit=self._max_per_tick
                )
                await session.commit()
            logger.info("Retry sweep complete.", extra={"extra_fields": {"dispatched": dispatched}})
            return dispatched
        except Exception as exc:
            logger.warning(
                "The retry sweep tick failed; the next tick will retry.",
                extra={"extra_fields": {"error": str(exc)}},
            )
            return 0


__all__ = ["RetrySweepWorker"]
