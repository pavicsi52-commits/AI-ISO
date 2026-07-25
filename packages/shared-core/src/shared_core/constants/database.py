"""Database-related constants."""

from typing import Final


class DatabaseConstants:
    """PostgreSQL and general database constants."""

    DEFAULT_PORT: Final[int] = 5432
    DEFAULT_POOL_MIN_SIZE: Final[int] = 5
    DEFAULT_POOL_MAX_SIZE: Final[int] = 20
    DEFAULT_POOL_TIMEOUT_SECONDS: Final[int] = 30
    DEFAULT_STATEMENT_TIMEOUT_SECONDS: Final[int] = 30
    DEFAULT_CONNECTION_RETRY_ATTEMPTS: Final[int] = 3

    EXTENSION_UUID_OSSP: Final[str] = "uuid-ossp"
    EXTENSION_PGCRYPTO: Final[str] = "pgcrypto"
    EXTENSION_PGVECTOR: Final[str] = "vector"
    EXTENSION_BTREE_GIN: Final[str] = "btree_gin"
    EXTENSION_CITEXT: Final[str] = "citext"

    AUDIT_LOG_RETENTION_DAYS: Final[int] = 365 * 7
    LOG_RETENTION_DAYS: Final[int] = 90
    REPORT_RETENTION_DAYS: Final[int] = 365
