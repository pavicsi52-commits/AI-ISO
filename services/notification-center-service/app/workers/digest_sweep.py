"""The digest sweep worker.

Builds and sends a bundled digest for every user who has opted into one
(``digest_frequency != NONE``), across every organization.
**Leader-elected** through ``shared_core.scheduler`` -- see
:mod:`app.workers.registrar`.

**One user, one session.** A digest failure for one user (a bad
template, an unreachable channel) must not poison the transaction the
next user's own digest needs, and a user silently skipped is worse than
one that visibly failed.

Runs every :attr:`~app.config.settings.NotificationServiceSettings
.digest_sweep_seconds`, which is deliberately much shorter than any
single user's own ``digest_frequency`` window --
:meth:`~app.services.digest.DigestService.build_and_send` itself decides
whether *this* tick is actually due for a given user by looking back
only ``digest_frequency``'s own window, so a frequent sweep tick is safe
to run against an infrequent per-user preference.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from shared_core.logging.logger import get_logger
from shared_core.notifications.manager import NotificationManager
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config.settings import NotificationServiceSettings
from app.repositories.notification import NotificationRepository
from app.repositories.preference import NotificationPreferenceRepository
from app.services.delivery import build_delivery_service
from app.services.digest import DigestService
from app.services.notification import NotificationService
from app.services.preference import PreferenceService

logger = get_logger("app.workers.digest_sweep")


class DigestSweepWorker:
    """Builds and sends every digest-subscribed user's own bundled digest."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        notification_manager: NotificationManager,
        settings: NotificationServiceSettings,
        *,
        max_per_tick: int = 1_000,
    ) -> None:
        self._session_factory = session_factory
        self._notification_manager = notification_manager
        self._settings = settings
        self._max_per_tick = max_per_tick

    async def run_job(self, _job: object) -> None:
        """Entry point matching ``shared_core.scheduler``'s own ``JobFn``."""
        await self.tick()

    async def tick(self) -> int:
        """Send every due digest; returns how many were sent."""
        subscribers = await self._subscribers()
        sent = 0
        for organization_id, user_id in subscribers:
            if await self._send_one(organization_id, user_id):
                sent += 1
        logger.info(
            "Digest sweep complete.",
            extra={"extra_fields": {"subscribers": len(subscribers), "sent": sent}},
        )
        return sent

    async def _subscribers(self) -> list[tuple[UUID, str]]:
        """Every ``(organization_id, user_id)`` pair with a digest preference set."""
        async with self._session_factory() as session:
            rows = await NotificationPreferenceRepository(session).list_digest_subscribers(
                limit=self._max_per_tick
            )
            return [(row.organization_id, row.user_id) for row in rows]

    async def _send_one(self, organization_id: UUID, user_id: str) -> bool:
        """Build and send one user's own digest under its own session."""
        try:
            async with self._session_factory() as session:
                delivery = build_delivery_service(session, self._notification_manager, self._settings)
                digest_service = DigestService(
                    NotificationRepository(session),
                    PreferenceService(NotificationPreferenceRepository(session)),
                    NotificationService(NotificationRepository(session)),
                    delivery,
                    max_items=self._settings.digest_max_items,
                )
                sent = await digest_service.build_and_send(
                    organization_id, user_id, now=datetime.now(UTC)
                )
                await session.commit()
            return sent is not None
        except Exception as exc:
            logger.warning(
                "A digest send failed for one user; the rest of the tick continues.",
                extra={"extra_fields": {"organization_id": str(organization_id), "error": str(exc)}},
            )
            return False


__all__ = ["DigestSweepWorker"]
