"""Connection lifecycle: retry-on-startup, graceful shutdown, automatic recovery.

Complements :mod:`shared_core.database.engine` (which only *constructs* an
engine): this module governs what happens *around* that engine's lifetime --
retrying a not-yet-ready database at process startup, and disposing the pool
cleanly at shutdown. Automatic recovery of individual dead connections is
handled transparently by the engine's ``pool_pre_ping`` (Prompt 018
"DATABASE ENGINE": "Automatic Recovery"); this module handles the
whole-database-unavailable case.
"""

from __future__ import annotations

import asyncio
import random

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from shared_core.database.constants import (
    DEFAULT_CONNECT_BACKOFF_BASE_SECONDS,
    DEFAULT_CONNECT_BACKOFF_MAX_SECONDS,
    DEFAULT_CONNECT_MAX_ATTEMPTS,
)
from shared_core.database.exceptions import ConnectionFailedError
from shared_core.logging import get_logger

logger = get_logger("shared_core.database.connection")


async def wait_for_database(
    engine: AsyncEngine,
    *,
    max_attempts: int = DEFAULT_CONNECT_MAX_ATTEMPTS,
    backoff_base_seconds: float = DEFAULT_CONNECT_BACKOFF_BASE_SECONDS,
    backoff_max_seconds: float = DEFAULT_CONNECT_BACKOFF_MAX_SECONDS,
) -> None:
    """Block until *engine* can serve a trivial query, retrying with backoff.

    Intended for service startup, where the database container may still be
    initializing. Raises :class:`ConnectionFailedError` once *max_attempts*
    is exhausted.
    """
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return
        except SQLAlchemyError as exc:
            last_error = exc
            if attempt == max_attempts:
                break
            delay = min(backoff_base_seconds * (2 ** (attempt - 1)), backoff_max_seconds)
            delay += random.uniform(0, backoff_base_seconds)
            logger.warning(
                "database connection attempt failed, retrying",
                extra={"attempt": attempt, "max_attempts": max_attempts, "delay_seconds": delay},
            )
            await asyncio.sleep(delay)

    raise ConnectionFailedError(
        f"Could not connect to the database after {max_attempts} attempts."
    ) from last_error


async def graceful_shutdown(engine: AsyncEngine) -> None:
    """Dispose *engine*'s connection pool, closing every pooled connection.

    Call once at service shutdown. Safe to call even if the engine was never
    successfully connected.
    """
    logger.info("closing database engine connection pool")
    await engine.dispose()


__all__ = ["graceful_shutdown", "wait_for_database"]
