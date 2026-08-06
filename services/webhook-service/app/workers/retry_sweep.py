"""The retry sweep worker.

Executes every due retry across every organization. **Leader-elected**
through ``shared_core.scheduler`` -- see :mod:`app.workers.registrar`.

**One session per retry.** A single endpoint's own failure must not
poison the transaction the next delivery's retry needs, and a retry
silently skipped is worse than one that visibly failed again.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import httpx
from shared_core.logging.logger import get_logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.repositories.delivery import WebhookDeliveryRepository
from app.repositories.retry import WebhookRetryQueueRepository
from app.services.delivery import build_delivery_service
from app.types import EventPublisher

logger = get_logger("app.workers.retry_sweep")


class RetrySweepWorker:
    """Executes every due retry, across every organization."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        http_client: httpx.AsyncClient,
        *,
        encryption_key: str,
        max_per_tick: int = 500,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._http_client = http_client
        self._encryption_key = encryption_key
        self._max_per_tick = max_per_tick
        self._publish = publish_event

    async def run_job(self, _job: object) -> None:
        """Entry point matching ``shared_core.scheduler``'s own ``JobFn``."""
        await self.tick()

    async def tick(self) -> int:
        """Retry every due delivery; returns how many attempts were made."""
        targets = await self._due_deliveries()
        attempted = 0
        for organization_id, delivery_id in targets:
            if await self._retry_one(organization_id, delivery_id):
                attempted += 1
        logger.info(
            "Retry sweep complete.",
            extra={"extra_fields": {"due": len(targets), "attempted": attempted}},
        )
        return attempted

    async def _due_deliveries(self) -> list[tuple[UUID, UUID]]:
        async with self._session_factory() as session:
            entries = await WebhookRetryQueueRepository(session).list_due(
                now=datetime.now(UTC), limit=self._max_per_tick
            )
            deliveries = WebhookDeliveryRepository(session)
            results = []
            for entry in entries:
                delivery = await deliveries.require_by_id(entry.delivery_id)
                results.append((delivery.organization_id, delivery.id))
            return results

    async def _retry_one(self, organization_id: UUID, delivery_id: UUID) -> bool:
        """Retry one delivery under its own session."""
        try:
            async with self._session_factory() as session:
                deliveries = WebhookDeliveryRepository(session)
                delivery = await deliveries.require_in_org(organization_id, delivery_id)
                service = build_delivery_service(
                    session,
                    self._http_client,
                    encryption_key=self._encryption_key,
                    publish_event=self._publish,
                )
                await service.deliver(organization_id, delivery)
                await session.commit()
            return True
        except Exception as exc:
            logger.warning(
                "A delivery retry failed; the rest of the sweep continues.",
                extra={
                    "extra_fields": {
                        "organization_id": str(organization_id),
                        "delivery_id": str(delivery_id),
                        "error": str(exc),
                    }
                },
            )
            return False


__all__ = ["RetrySweepWorker"]
