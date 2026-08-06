"""The signing-secret expiry sweep worker.

Moves every ``ROTATING`` secret whose own overlap window has ended to
``EXPIRED``, across every organization, in one tick. **Leader-elected**
through ``shared_core.scheduler`` -- see :mod:`app.workers.registrar`.
"""

from __future__ import annotations

from datetime import UTC, datetime

from shared_core.logging.logger import get_logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.repositories.signature import WebhookSignatureRepository
from app.services.signature import SignatureService

logger = get_logger("app.workers.secret_expiry_sweep")


class SecretExpirySweepWorker:
    """Expires every rotating signing secret whose own overlap window has ended."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        encryption_key: str,
        max_per_tick: int = 500,
    ) -> None:
        self._session_factory = session_factory
        self._encryption_key = encryption_key
        self._max_per_tick = max_per_tick

    async def run_job(self, _job: object) -> None:
        """Entry point matching ``shared_core.scheduler``'s own ``JobFn``."""
        await self.tick()

    async def tick(self) -> int:
        """Expire every due rotating secret; returns how many were expired."""
        try:
            async with self._session_factory() as session:
                service = SignatureService(
                    WebhookSignatureRepository(session), encryption_key=self._encryption_key
                )
                expired = await service.expire_due(now=datetime.now(UTC), limit=self._max_per_tick)
                await session.commit()
        except Exception as exc:
            logger.warning(
                "The secret expiry sweep failed.", extra={"extra_fields": {"error": str(exc)}}
            )
            return 0
        logger.info("Secret expiry sweep complete.", extra={"extra_fields": {"expired": expired}})
        return expired


__all__ = ["SecretExpirySweepWorker"]
