"""Database-framework connection-pool configuration.

Adapts :class:`shared_core.config.settings.DatabaseSettings` (Prompt 013)
into the pool-shaped configuration :mod:`shared_core.database.engine` and
:mod:`shared_core.database.connection` need, applying this framework's
defaults (:mod:`shared_core.database.constants`) for anything the
Configuration Framework doesn't itself expose. This is an adapter, not a
duplicate settings source -- the DSN and credentials always come from
:class:`~shared_core.config.settings.DatabaseSettings`.
"""

from __future__ import annotations

from dataclasses import dataclass

from shared_core.config.settings import DatabaseSettings
from shared_core.database.constants import (
    DEFAULT_CONNECT_BACKOFF_BASE_SECONDS,
    DEFAULT_CONNECT_BACKOFF_MAX_SECONDS,
    DEFAULT_CONNECT_MAX_ATTEMPTS,
    DEFAULT_POOL_RECYCLE_SECONDS,
    DEFAULT_POOL_TIMEOUT_SECONDS,
)


@dataclass(frozen=True, slots=True)
class ConnectionPoolSettings:
    """Fully-resolved connection-pool configuration for one database engine."""

    dsn: str
    pool_min: int
    pool_max: int
    pool_timeout_seconds: float
    pool_recycle_seconds: int
    connect_max_attempts: int
    connect_backoff_base_seconds: float
    connect_backoff_max_seconds: float

    @property
    def max_overflow(self) -> int:
        """Additional connections allowed beyond ``pool_min`` under load."""
        return max(self.pool_max - self.pool_min, 0)


def build_pool_settings(
    settings: DatabaseSettings,
    *,
    pool_timeout_seconds: float = DEFAULT_POOL_TIMEOUT_SECONDS,
    pool_recycle_seconds: int = DEFAULT_POOL_RECYCLE_SECONDS,
    connect_max_attempts: int = DEFAULT_CONNECT_MAX_ATTEMPTS,
    connect_backoff_base_seconds: float = DEFAULT_CONNECT_BACKOFF_BASE_SECONDS,
    connect_backoff_max_seconds: float = DEFAULT_CONNECT_BACKOFF_MAX_SECONDS,
) -> ConnectionPoolSettings:
    """Resolve :class:`ConnectionPoolSettings` from the Configuration Framework."""
    return ConnectionPoolSettings(
        dsn=settings.dsn,
        pool_min=settings.database_pool_min,
        pool_max=settings.database_pool_max,
        pool_timeout_seconds=pool_timeout_seconds,
        pool_recycle_seconds=pool_recycle_seconds,
        connect_max_attempts=connect_max_attempts,
        connect_backoff_base_seconds=connect_backoff_base_seconds,
        connect_backoff_max_seconds=connect_backoff_max_seconds,
    )


__all__ = ["ConnectionPoolSettings", "build_pool_settings"]
