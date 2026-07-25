"""Enterprise Cache Framework constants.

Single source of truth for TTL, pool, retry/backoff, compression, and lock
defaults used across the framework, per
docs/019_Enterprise_Cache_Framework.md.txt.
"""

from __future__ import annotations

from typing import Final

# Key namespacing
KEY_PREFIX: Final[str] = "aiios"
KEY_SEPARATOR: Final[str] = ":"
MAX_KEY_LENGTH: Final[int] = 512

# TTL
DEFAULT_TTL_SECONDS: Final[int] = 300
MIN_TTL_SECONDS: Final[int] = 1
MAX_TTL_SECONDS: Final[int] = 60 * 60 * 24 * 30  # 30 days

# Connection pool
DEFAULT_POOL_MIN_SIZE: Final[int] = 5
DEFAULT_POOL_MAX_SIZE: Final[int] = 50
DEFAULT_SOCKET_TIMEOUT_SECONDS: Final[float] = 5.0
DEFAULT_SOCKET_CONNECT_TIMEOUT_SECONDS: Final[float] = 5.0

# Connection retry / backoff
DEFAULT_CONNECT_MAX_ATTEMPTS: Final[int] = 5
DEFAULT_CONNECT_BACKOFF_BASE_SECONDS: Final[float] = 0.5
DEFAULT_CONNECT_BACKOFF_MAX_SECONDS: Final[float] = 10.0

# Distributed locks
DEFAULT_LOCK_TTL_SECONDS: Final[int] = 30
DEFAULT_LOCK_MAX_RETRIES: Final[int] = 50
DEFAULT_LOCK_RETRY_DELAY_SECONDS: Final[float] = 0.1
DEFAULT_LOCK_RENEWAL_MARGIN_SECONDS: Final[float] = 5.0
DEFAULT_LOCK_CLOCK_DRIFT_FACTOR: Final[float] = 0.01  # Redlock validity-time safety margin

# Compression
DEFAULT_COMPRESSION_THRESHOLD_BYTES: Final[int] = 1024
DEFAULT_ZSTD_LEVEL: Final[int] = 3
DEFAULT_GZIP_LEVEL: Final[int] = 6

# Rate limiting
DEFAULT_RATE_LIMIT_WINDOW_SECONDS: Final[int] = 60
DEFAULT_RATE_LIMIT_MAX_REQUESTS: Final[int] = 100
DEFAULT_RATE_LIMIT_PENALTY_SECONDS: Final[int] = 60

# Sessions
DEFAULT_SESSION_IDLE_TIMEOUT_SECONDS: Final[int] = 60 * 30
DEFAULT_SESSION_ABSOLUTE_TIMEOUT_SECONDS: Final[int] = 60 * 60 * 12

# Feature flags
DEFAULT_FEATURE_FLAG_TTL_SECONDS: Final[int] = 60

# Health
DEFAULT_HEALTH_CHECK_TIMEOUT_SECONDS: Final[float] = 5.0
SLOW_OPERATION_THRESHOLD_MS: Final[float] = 50.0

# Warmup
DEFAULT_WARMUP_CONCURRENCY: Final[int] = 10
