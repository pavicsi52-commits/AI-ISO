"""The replay processor worker.

Executes every pending replay job. **Leader-elected** through
``shared_core.scheduler`` -- see :mod:`app.workers.registrar`.

**One session per job.** A single bad job (a broken filter, an
unreachable endpoint mid-replay) must not poison the transaction the
next job needs.
"""

from __future__ import annotations

from uuid import UUID

import httpx
from shared_core.logging.logger import get_logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.repositories.event import WebhookEventRepository
from app.repositories.replay import WebhookReplayJobRepository
from app.services.delivery import build_delivery_service
from app.services.replay import ReplayService

logger = get_logger("app.workers.replay_processor")


class ReplayProcessorWorker:
    """Processes every pending replay job."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        http_client: httpx.AsyncClient,
        *,
        encryption_key: str,
        max_per_tick: int = 20,
    ) -> None:
        self._session_factory = session_factory
        self._http_client = http_client
        self._encryption_key = encryption_key
        self._max_per_tick = max_per_tick

    async def run_job(self, _job: object) -> None:
        """Entry point matching ``shared_core.scheduler``'s own ``JobFn``."""
        await self.tick()

    async def tick(self) -> int:
        """Run every pending replay job; returns how many were processed."""
        targets = await self._pending_jobs()
        processed = 0
        for organization_id, job_id in targets:
            if await self._run_one(organization_id, job_id):
                processed += 1
        logger.info(
            "Replay processor sweep complete.",
            extra={"extra_fields": {"pending": len(targets), "processed": processed}},
        )
        return processed

    async def _pending_jobs(self) -> list[tuple[UUID, UUID]]:
        async with self._session_factory() as session:
            jobs = await WebhookReplayJobRepository(session).list_pending(limit=self._max_per_tick)
            return [(job.organization_id, job.id) for job in jobs]

    async def _run_one(self, organization_id: UUID, job_id: UUID) -> bool:
        """Run one replay job under its own session."""
        try:
            async with self._session_factory() as session:
                delivery = build_delivery_service(
                    session, self._http_client, encryption_key=self._encryption_key
                )
                service = ReplayService(
                    WebhookReplayJobRepository(session), WebhookEventRepository(session), delivery
                )
                await service.run(organization_id, job_id)
                await session.commit()
            return True
        except Exception as exc:
            logger.warning(
                "A replay job failed; the rest of the sweep continues.",
                extra={
                    "extra_fields": {
                        "organization_id": str(organization_id),
                        "job_id": str(job_id),
                        "error": str(exc),
                    }
                },
            )
            return False


__all__ = ["ReplayProcessorWorker"]
