"""Database health checks.

Per docs/018_Enterprise_Database_Framework.md.txt "DATABASE HEALTH":
Connection Test, Latency, Version, Pool Status. (Replication Status and
Disk Usage are explicitly listed as future work, so are not implemented
here.)
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from shared_core.enums.health_status import HealthStatus


async def check_database_health(engine: AsyncEngine) -> tuple[HealthStatus, float]:
    """Check database connectivity and measure round-trip latency.

    Returns:
        A ``(status, latency_ms)`` tuple. Status is ``UNHEALTHY`` if the
        connection attempt raises.
    """
    start = time.perf_counter()
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        return HealthStatus.UNHEALTHY, round((time.perf_counter() - start) * 1000, 2)
    return HealthStatus.HEALTHY, round((time.perf_counter() - start) * 1000, 2)


@dataclass(frozen=True, slots=True)
class PoolStatus:
    """Connection pool utilization at the moment of a health check."""

    size: int
    checked_in: int
    checked_out: int
    overflow: int


@dataclass(frozen=True, slots=True)
class DatabaseHealthReport:
    """Full database health snapshot: connectivity, latency, version, pool status."""

    status: HealthStatus
    latency_ms: float
    server_version: str | None
    pool: PoolStatus


def get_pool_status(engine: AsyncEngine) -> PoolStatus:
    """Return the current connection pool's utilization counters.

    Guarded with ``hasattr`` because not every pool implementation exposes
    all four counters (e.g. a test engine's ``NullPool`` doesn't track
    checked-in/out counts the way ``QueuePool`` does).
    """
    pool = engine.pool
    return PoolStatus(
        size=pool.size() if hasattr(pool, "size") else 0,
        checked_in=pool.checkedin() if hasattr(pool, "checkedin") else 0,
        checked_out=pool.checkedout() if hasattr(pool, "checkedout") else 0,
        overflow=pool.overflow() if hasattr(pool, "overflow") else 0,
    )


async def get_health_report(engine: AsyncEngine) -> DatabaseHealthReport:
    """Run the full "DATABASE HEALTH" check set against *engine*."""
    status, latency_ms = await check_database_health(engine)
    server_version: str | None = None
    if status is HealthStatus.HEALTHY:
        try:
            async with engine.connect() as conn:
                result = await conn.execute(text("SHOW server_version"))
                server_version = result.scalar_one_or_none()
        except Exception:
            server_version = None
    return DatabaseHealthReport(
        status=status,
        latency_ms=latency_ms,
        server_version=server_version,
        pool=get_pool_status(engine),
    )


__all__ = [
    "DatabaseHealthReport",
    "PoolStatus",
    "check_database_health",
    "get_health_report",
    "get_pool_status",
]
