"""Redis-related constants."""

from typing import Final


class RedisConstants:
    """Redis connection and cache constants."""

    DEFAULT_PORT: Final[int] = 6379
    DEFAULT_DB: Final[int] = 0
    DEFAULT_TTL_SECONDS: Final[int] = 300
    DEFAULT_LOCK_TTL_SECONDS: Final[int] = 30
    DEFAULT_LOCK_RETRY_DELAY_SECONDS: Final[float] = 0.1
    DEFAULT_LOCK_MAX_RETRIES: Final[int] = 50
    KEY_PREFIX: Final[str] = "aiios"
    KEY_SEPARATOR: Final[str] = ":"
