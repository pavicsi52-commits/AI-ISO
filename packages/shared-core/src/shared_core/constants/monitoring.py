"""Monitoring-related constants."""

from typing import Final


class MonitoringConstants:
    """Health check and metrics constants."""

    DEFAULT_HEALTH_CHECK_TIMEOUT_SECONDS: Final[float] = 5.0
    DEFAULT_DEPENDENCY_CHECK_INTERVAL_SECONDS: Final[int] = 30
    METRICS_NAMESPACE: Final[str] = "aiios"
