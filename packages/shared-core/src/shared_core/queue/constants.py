"""Enterprise Queue Framework constants.

Single source of truth for retry/backoff, priority, delay, and naming
conventions used across the framework, per
docs/021_Enterprise_Queue_Framework.md.txt.
"""

from __future__ import annotations

from typing import Final

from shared_core.enums.priority import Priority

# Naming (suffixes appended to a base queue name)
DEAD_LETTER_QUEUE_SUFFIX: Final[str] = ".dlq"
DELAY_QUEUE_SUFFIX: Final[str] = ".delay"
RETRY_HEADER: Final[str] = "x-retry-count"
DELAY_HEADER: Final[str] = "x-delay-ms"
PRIORITY_HEADER: Final[str] = "x-priority-level"
SCHEDULED_FOR_HEADER: Final[str] = "x-scheduled-for"

# Connection management
DEFAULT_PREFETCH_COUNT: Final[int] = 10
DEFAULT_HEARTBEAT_SECONDS: Final[int] = 60
DEFAULT_CONNECT_MAX_ATTEMPTS: Final[int] = 5
DEFAULT_CONNECT_BACKOFF_BASE_SECONDS: Final[float] = 0.5
DEFAULT_CONNECT_BACKOFF_MAX_SECONDS: Final[float] = 30.0
DEFAULT_CONNECTION_POOL_SIZE: Final[int] = 4
DEFAULT_CHANNEL_POOL_SIZE: Final[int] = 10

# Retry
DEFAULT_RETRY_MAX_ATTEMPTS: Final[int] = 5
DEFAULT_RETRY_BACKOFF_BASE_SECONDS: Final[float] = 1.0
DEFAULT_RETRY_BACKOFF_MAX_SECONDS: Final[float] = 60.0
DEFAULT_RETRY_BACKOFF_MULTIPLIER: Final[float] = 2.0

# Priority: RabbitMQ's native `x-max-priority` queue argument, and the
# numeric level each framework Priority maps to within that range (0-9;
# higher runs first). Five framework levels leave headroom between them.
PRIORITY_QUEUE_MAX_PRIORITY: Final[int] = 9
PRIORITY_LEVELS: Final[dict[Priority, int]] = {
    Priority.CRITICAL: 9,
    Priority.HIGH: 7,
    Priority.NORMAL: 4,
    Priority.LOW: 2,
    Priority.BACKGROUND: 0,
}

# Delay
MIN_DELAY_MILLISECONDS: Final[int] = 0
MAX_DELAY_MILLISECONDS: Final[int] = 1000 * 60 * 60 * 24 * 7  # 7 days

# Dead letter inspection/replay
DEFAULT_DEAD_LETTER_INSPECT_LIMIT: Final[int] = 100
DEFAULT_DEAD_LETTER_GET_TIMEOUT_SECONDS: Final[float] = 1.0

# Worker pool
DEFAULT_MIN_WORKERS: Final[int] = 1
DEFAULT_MAX_WORKERS: Final[int] = 10
DEFAULT_WORKER_HEALTH_CHECK_INTERVAL_SECONDS: Final[float] = 10.0
DEFAULT_WORKER_RESTART_BACKOFF_SECONDS: Final[float] = 1.0

# Scheduler
DEFAULT_SCHEDULER_POLL_INTERVAL_SECONDS: Final[float] = 1.0

# Consumer
DEFAULT_BATCH_FLUSH_INTERVAL_SECONDS: Final[float] = 1.0

# Health
DEFAULT_HEALTH_CHECK_TIMEOUT_SECONDS: Final[float] = 5.0

# Serialization / compression
DEFAULT_PAYLOAD_COMPRESSION_THRESHOLD_BYTES: Final[int] = 4096

# Statistics
DEFAULT_STATISTICS_WINDOW_SIZE: Final[int] = 1000
