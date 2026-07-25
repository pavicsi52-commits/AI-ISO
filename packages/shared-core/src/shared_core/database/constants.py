"""Enterprise Database Framework constants.

Single source of truth for pool sizing, retry/backoff, timeout, and
PostgreSQL SQLSTATE codes used across the framework, per
docs/018_Enterprise_Database_Framework.md.txt.
"""

from __future__ import annotations

from typing import Final

# PostgreSQL SQLSTATE error codes (https://www.postgresql.org/docs/current/errcodes-appendix.html)
POSTGRES_UNIQUE_VIOLATION: Final[str] = "23505"
POSTGRES_FOREIGN_KEY_VIOLATION: Final[str] = "23503"
POSTGRES_CHECK_VIOLATION: Final[str] = "23514"
POSTGRES_NOT_NULL_VIOLATION: Final[str] = "23502"
POSTGRES_DEADLOCK_DETECTED: Final[str] = "40P01"
POSTGRES_SERIALIZATION_FAILURE: Final[str] = "40001"
POSTGRES_QUERY_CANCELED: Final[str] = "57014"
POSTGRES_ADMIN_SHUTDOWN: Final[str] = "57P01"
POSTGRES_CONNECTION_FAILURE: Final[str] = "08006"

RETRYABLE_SQLSTATES: Final[frozenset[str]] = frozenset(
    {
        POSTGRES_DEADLOCK_DETECTED,
        POSTGRES_SERIALIZATION_FAILURE,
        POSTGRES_CONNECTION_FAILURE,
    }
)
CONSTRAINT_SQLSTATES: Final[frozenset[str]] = frozenset(
    {
        POSTGRES_UNIQUE_VIOLATION,
        POSTGRES_FOREIGN_KEY_VIOLATION,
        POSTGRES_CHECK_VIOLATION,
        POSTGRES_NOT_NULL_VIOLATION,
    }
)

# Connection pool defaults (overridden by shared_core.config.settings.DatabaseSettings)
DEFAULT_POOL_MIN: Final[int] = 5
DEFAULT_POOL_MAX: Final[int] = 20
DEFAULT_POOL_TIMEOUT_SECONDS: Final[float] = 30.0
DEFAULT_POOL_RECYCLE_SECONDS: Final[int] = 1800

# Connection retry / backoff
DEFAULT_CONNECT_MAX_ATTEMPTS: Final[int] = 5
DEFAULT_CONNECT_BACKOFF_BASE_SECONDS: Final[float] = 0.5
DEFAULT_CONNECT_BACKOFF_MAX_SECONDS: Final[float] = 10.0

# Transaction retry / backoff (deadlocks, serialization failures)
DEFAULT_TRANSACTION_MAX_ATTEMPTS: Final[int] = 3
DEFAULT_TRANSACTION_BACKOFF_BASE_SECONDS: Final[float] = 0.05
DEFAULT_TRANSACTION_BACKOFF_MAX_SECONDS: Final[float] = 1.0
DEFAULT_TRANSACTION_TIMEOUT_SECONDS: Final[float] = 30.0

# Pagination
DEFAULT_PAGE_SIZE: Final[int] = 20
MAX_PAGE_SIZE: Final[int] = 200
DEFAULT_PAGE_NUMBER: Final[int] = 1

# Search
DEFAULT_TRIGRAM_SIMILARITY_THRESHOLD: Final[float] = 0.3
DEFAULT_FULL_TEXT_LANGUAGE: Final[str] = "english"

# Slow query logging
DEFAULT_SLOW_QUERY_THRESHOLD_MS: Final[float] = 200.0
