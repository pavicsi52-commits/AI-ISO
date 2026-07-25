"""Enterprise Event Framework constants.

Single source of truth for retry/backoff, replay retention, and queue
naming used across the framework, per
docs/020_Enterprise_Event_Framework.md.txt.
"""

from __future__ import annotations

from typing import Final

# Queue naming (must match shared_core.queue's dead-letter naming convention)
EVENT_QUEUE_PREFIX: Final[str] = "events"
DEAD_LETTER_QUEUE_SUFFIX: Final[str] = ".dlq"

# Retry
DEFAULT_RETRY_MAX_ATTEMPTS: Final[int] = 5
DEFAULT_RETRY_BACKOFF_BASE_SECONDS: Final[float] = 0.5
DEFAULT_RETRY_BACKOFF_MAX_SECONDS: Final[float] = 30.0

# Replay / event store retention
DEFAULT_REPLAY_RETENTION_SECONDS: Final[int] = 60 * 60 * 24 * 7  # 7 days
DEFAULT_REPLAY_LIMIT: Final[int] = 1000
MAX_REPLAY_LIMIT: Final[int] = 10_000

# Dead letter inspection/replay
DEFAULT_DEAD_LETTER_INSPECT_LIMIT: Final[int] = 100
DEFAULT_DEAD_LETTER_GET_TIMEOUT_SECONDS: Final[float] = 1.0

# Dispatcher
DEFAULT_HANDLER_PRIORITY: Final[int] = 100  # lower runs first

# Health
DEFAULT_HEALTH_CHECK_TIMEOUT_SECONDS: Final[float] = 5.0

# Serialization / compression (large-payload compaction)
DEFAULT_PAYLOAD_COMPRESSION_THRESHOLD_BYTES: Final[int] = 4096
