"""Async SQLAlchemy engine creation.

PostgreSQL only, per docs/018_Enterprise_Database_Framework.md.txt
"DATABASE ENGINE". Pool sizing comes from the Configuration Framework via
:mod:`shared_core.database.settings`; ``pool_pre_ping`` gives every checked-out
connection automatic liveness validation (dead connections are transparently
replaced rather than surfacing as query errors), and ``pool_recycle`` avoids
connections going stale behind load balancers/firewalls that silently drop
long-idle TCP connections.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from shared_core.config.settings import DatabaseSettings
from shared_core.database.settings import ConnectionPoolSettings, build_pool_settings


def create_engine(settings: DatabaseSettings, *, echo: bool = False) -> AsyncEngine:
    """Create an async SQLAlchemy engine with connection pooling.

    Args:
        settings: Database connection settings.
        echo: Whether to log all emitted SQL (development only).
    """
    return create_engine_from_pool_settings(build_pool_settings(settings), echo=echo)


def create_engine_from_pool_settings(
    pool_settings: ConnectionPoolSettings, *, echo: bool = False
) -> AsyncEngine:
    """Create an async engine from fully-resolved :class:`ConnectionPoolSettings`.

    Split out from :func:`create_engine` so callers that need non-default
    pool tuning (e.g. a background worker wanting a smaller pool) don't have
    to construct a full :class:`~shared_core.config.settings.DatabaseSettings`.
    """
    return create_async_engine(
        pool_settings.dsn,
        echo=echo,
        pool_size=pool_settings.pool_min,
        max_overflow=pool_settings.max_overflow,
        pool_timeout=pool_settings.pool_timeout_seconds,
        pool_recycle=pool_settings.pool_recycle_seconds,
        pool_pre_ping=True,
    )


def create_test_engine(dsn: str, *, echo: bool = False) -> AsyncEngine:
    """Create an async engine for a test database (e.g. an in-memory SQLite DSN).

    SQLite does not support the pool-size/overflow options used by
    :func:`create_engine`, so this is a separate, minimal constructor for
    tests rather than a code path shared with production.
    """
    return create_async_engine(dsn, echo=echo)


__all__ = ["create_engine", "create_engine_from_pool_settings", "create_test_engine"]
