"""The idempotency-key expiry sweep worker.

Marks every idempotency key whose own expiry has passed as ``EXPIRED``,
across every organization, in one tick. **Leader-elected** through
``shared_core.scheduler`` -- see :mod:`app.workers.registrar`.
"""

from __future__ import annotations

from datetime import UTC, datetime

from shared_core.logging.logger import get_logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.repositories.idempotency import WebhookIdempotencyKeyRepository
from app.services.idempotency import IdempotencyService

logger = get_logger("app.workers.idempotency_sweep")


class IdempotencyExpirySweepWorker:
    """Expires every idempotency key whose own TTL has passed."""

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], *, max_per_tick: int = 500
    ) -> None:
        self._session_factory = session_factory
        self._max_per_tick = max_per_tick

    async def run_job(self, _job: object) -> None:
        """Entry point matching ``shared_core.scheduler``'s own ``JobFn``."""
        await self.tick()

    async def tick(self) -> int:
        """Expire every due key; returns how many were expired."""
        try:
            async with self._session_factory() as session:
                service = IdempotencyService(
                    WebhookIdempotencyKeyRepository(session), ttl_seconds=0
                )
                expired = await service.expire_due(now=datetime.now(UTC), limit=self._max_per_tick)
                await session.commit()
        except Exception as exc:
            logger.warning(
                "The idempotency expiry sweep failed.", extra={"extra_fields": {"error": str(exc)}}
            )
            return 0
        logger.info(
            "Idempotency expiry sweep complete.", extra={"extra_fields": {"expired": expired}}
        )
        return expired


__all__ = ["IdempotencyExpirySweepWorker"]
