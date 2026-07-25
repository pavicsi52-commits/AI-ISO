"""Enterprise Scheduler Framework constants.

Single source of truth for polling intervals, lock TTLs, retry, and
history defaults used across the framework, per
docs/026_Enterprise_Scheduler_Framework.md.txt.
"""

from __future__ import annotations

from typing import Final

# Engine polling ("PERFORMANCE": Async Scheduler)
DEFAULT_POLL_INTERVAL_SECONDS: Final[float] = 1.0

# Job execution ("JOB EXECUTION": Timeout)
DEFAULT_JOB_TIMEOUT_SECONDS: Final[float] = 300.0

# Retry ("RETRY POLICY")
DEFAULT_RETRY_MAX_ATTEMPTS: Final[int] = 3

# Distributed locking / leader election ("DISTRIBUTED SCHEDULING")
DEFAULT_JOB_LOCK_TTL_SECONDS: Final[int] = 60
DEFAULT_LEADER_LOCK_TTL_SECONDS: Final[int] = 15
DEFAULT_LEADER_RENEW_INTERVAL_SECONDS: Final[float] = 5.0

# Heartbeat / failover ("HIGH AVAILABILITY")
DEFAULT_HEARTBEAT_INTERVAL_SECONDS: Final[float] = 10.0
DEFAULT_HEARTBEAT_TIMEOUT_SECONDS: Final[float] = 30.0

# History ("HISTORY")
DEFAULT_HISTORY_BUFFER_SIZE: Final[int] = 5_000

# Worker ("PERFORMANCE": Distributed Workers)
DEFAULT_MAX_CONCURRENT_JOBS_PER_WORKER: Final[int] = 10
