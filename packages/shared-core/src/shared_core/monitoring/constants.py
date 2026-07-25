"""Enterprise Monitoring Framework constants.

Single source of truth for polling intervals, cache TTLs, and threshold
defaults used across the framework, per
docs/023_Enterprise_Monitoring_Framework.md.txt.
"""

from __future__ import annotations

from typing import Final

# Health checks ("PERFORMANCE": "Cached health checks", "Efficient polling")
DEFAULT_HEALTH_CHECK_TIMEOUT_SECONDS: Final[float] = 5.0
DEFAULT_HEALTH_CHECK_CACHE_SECONDS: Final[float] = 5.0

# Collection / heartbeat
DEFAULT_COLLECTION_INTERVAL_SECONDS: Final[float] = 15.0
DEFAULT_HEARTBEAT_INTERVAL_SECONDS: Final[float] = 30.0

# Application monitoring
DEFAULT_EVENT_LOOP_DELAY_SAMPLE_SECONDS: Final[float] = 0.05
DEFAULT_RESPONSE_TIME_SAMPLE_WINDOW: Final[int] = 1000

# Availability ("AVAILABILITY": Daily/Weekly/Monthly/Quarterly/Yearly)
DEFAULT_AVAILABILITY_WINDOW_SECONDS: Final[int] = 60 * 60 * 24 * 400  # >1 year rolling

# SLA defaults ("SLA MONITORING": Service Level Objectives)
DEFAULT_SLA_TARGET_AVAILABILITY_PERCENT: Final[float] = 99.9
DEFAULT_SLA_TARGET_RESPONSE_TIME_MS: Final[float] = 500.0
DEFAULT_SLA_TARGET_ERROR_RATE_PERCENT: Final[float] = 1.0

# Thresholds ("THRESHOLDS": Critical/High/Medium/Low/Informational)
DEFAULT_CPU_WARNING_PERCENT: Final[float] = 75.0
DEFAULT_CPU_CRITICAL_PERCENT: Final[float] = 90.0
DEFAULT_MEMORY_WARNING_PERCENT: Final[float] = 75.0
DEFAULT_MEMORY_CRITICAL_PERCENT: Final[float] = 90.0
DEFAULT_DISK_WARNING_PERCENT: Final[float] = 80.0
DEFAULT_DISK_CRITICAL_PERCENT: Final[float] = 95.0

# Synthetic / dependency checks
DEFAULT_DEPENDENCY_CHECK_RETRIES: Final[int] = 1
