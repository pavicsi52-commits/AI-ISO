"""The marketplace-approval sweep worker.

Auto-approves draft marketplace listings whose underlying plugin has
already cleared the registration/validation/publishing lifecycle
(``PUBLISHED`` or later) -- the review gate that actually matters
(manifest validation) already happened in
``PluginService.submit_manifest``/``publish``; a listing sitting in
``DRAFT`` for a plugin that's already been published to the platform is
just administrative lag, not a pending editorial decision. **Leader-elected**
through ``shared_core.scheduler`` -- see :mod:`app.workers.registrar`.

**One session per listing.** A single listing's own approval must not
poison the transaction the next listing's own approval needs.
"""

from __future__ import annotations

from uuid import UUID

from shared_core.logging.logger import get_logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.enums import PluginLifecycleStatus
from app.repositories.marketplace import PluginMarketplaceRepository
from app.repositories.plugin import PluginRepository
from app.services.marketplace import PluginMarketplaceService
from app.types import EventPublisher

logger = get_logger("app.workers.marketplace_approval_sweep")

_ELIGIBLE_STATUSES = frozenset({PluginLifecycleStatus.PUBLISHED, PluginLifecycleStatus.APPROVED})


class MarketplaceApprovalSweepWorker:
    """Auto-approves draft listings for already-published plugins."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        max_per_tick: int = 500,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._max_per_tick = max_per_tick
        self._publish = publish_event

    async def run_job(self, _job: object) -> None:
        """Entry point matching ``shared_core.scheduler``'s own ``JobFn``."""
        await self.tick()

    async def tick(self) -> int:
        """Approve every eligible draft listing; returns how many were approved."""
        entry_ids = await self._due_entries()
        approved = 0
        for entry_id in entry_ids:
            if await self._approve_one(entry_id):
                approved += 1
        logger.info(
            "Marketplace approval sweep complete.",
            extra={"extra_fields": {"pending": len(entry_ids), "approved": approved}},
        )
        return approved

    async def _due_entries(self) -> list[UUID]:
        async with self._session_factory() as session:
            rows = await PluginMarketplaceRepository(session).list_pending_approval(
                limit=self._max_per_tick
            )
            return [row.id for row in rows]

    async def _approve_one(self, entry_id: UUID) -> bool:
        try:
            async with self._session_factory() as session:
                marketplace_repo = PluginMarketplaceRepository(session)
                entry = await marketplace_repo.require_by_id(entry_id)
                plugin = await PluginRepository(session).require_by_id(entry.plugin_id)
                if plugin.status not in _ELIGIBLE_STATUSES:
                    return False
                service = PluginMarketplaceService(marketplace_repo, publish_event=self._publish)
                await service.approve(plugin.organization_id, entry_id, approved_by="system-sweep")
                await session.commit()
            return True
        except Exception as exc:
            logger.warning(
                "A marketplace listing auto-approval failed; the rest of the sweep continues.",
                extra={"extra_fields": {"entry_id": str(entry_id), "error": str(exc)}},
            )
            return False


__all__ = ["MarketplaceApprovalSweepWorker"]
