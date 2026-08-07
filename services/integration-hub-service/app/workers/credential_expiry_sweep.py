"""The credential expiry sweep worker.

Marks every ``ACTIVE`` credential whose own ``expires_at`` has passed
``EXPIRED``, across every organization, in one tick. **Leader-elected**
through ``shared_core.scheduler`` -- see :mod:`app.workers.registrar`.
"""

from __future__ import annotations

from datetime import UTC, datetime

from shared_core.logging.logger import get_logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.repositories.credential import ConnectorCredentialRepository
from app.services.credential import CredentialService

logger = get_logger("app.workers.credential_expiry_sweep")


class CredentialExpirySweepWorker:
    """Expires every credential whose own ``expires_at`` has passed."""

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
        """Expire every due credential; returns how many were expired."""
        try:
            async with self._session_factory() as session:
                service = CredentialService(
                    ConnectorCredentialRepository(session), encryption_key=self._encryption_key
                )
                due = await service.list_expiring_before(
                    datetime.now(UTC), limit=self._max_per_tick
                )
                for credential in due:
                    await service.mark_expired(credential)
                await session.commit()
        except Exception as exc:
            logger.warning(
                "The credential expiry sweep failed.", extra={"extra_fields": {"error": str(exc)}}
            )
            return 0
        logger.info(
            "Credential expiry sweep complete.", extra={"extra_fields": {"expired": len(due)}}
        )
        return len(due)


__all__ = ["CredentialExpirySweepWorker"]
