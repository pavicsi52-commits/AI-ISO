"""Thresholds.

Per docs/023_Enterprise_Monitoring_Framework.md.txt "THRESHOLDS":
Critical, High, Medium, Low, Informational. "Thresholds shall be
configurable."
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from shared_core.monitoring.constants import (
    DEFAULT_CPU_CRITICAL_PERCENT,
    DEFAULT_CPU_WARNING_PERCENT,
    DEFAULT_DISK_CRITICAL_PERCENT,
    DEFAULT_DISK_WARNING_PERCENT,
    DEFAULT_MEMORY_CRITICAL_PERCENT,
    DEFAULT_MEMORY_WARNING_PERCENT,
)


class ThresholdLevel(StrEnum):
    """Severity level a metric value can breach, per docs/023 "THRESHOLDS"."""

    INFORMATIONAL = "informational"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class Threshold:
    """One metric's configured breach levels. Any subset of levels may be set."""

    metric_name: str
    informational: float | None = None
    low: float | None = None
    medium: float | None = None
    high: float | None = None
    critical: float | None = None

    def evaluate(self, value: float) -> ThresholdLevel | None:
        """Return the highest-severity level *value* breaches, or ``None`` if it breaches none."""
        for level, limit in (
            (ThresholdLevel.CRITICAL, self.critical),
            (ThresholdLevel.HIGH, self.high),
            (ThresholdLevel.MEDIUM, self.medium),
            (ThresholdLevel.LOW, self.low),
            (ThresholdLevel.INFORMATIONAL, self.informational),
        ):
            if limit is not None and value >= limit:
                return level
        return None


def default_cpu_threshold() -> Threshold:
    """The framework's default CPU-usage threshold ("RESOURCE MONITORING": CPU)."""
    return Threshold(
        metric_name="cpu_percent",
        high=DEFAULT_CPU_WARNING_PERCENT,
        critical=DEFAULT_CPU_CRITICAL_PERCENT,
    )


def default_memory_threshold() -> Threshold:
    """The framework's default memory-usage threshold ("RESOURCE MONITORING": Memory)."""
    return Threshold(
        metric_name="memory_percent",
        high=DEFAULT_MEMORY_WARNING_PERCENT,
        critical=DEFAULT_MEMORY_CRITICAL_PERCENT,
    )


def default_disk_threshold() -> Threshold:
    """The framework's default disk-usage threshold ("RESOURCE MONITORING": Disk)."""
    return Threshold(
        metric_name="disk_percent",
        high=DEFAULT_DISK_WARNING_PERCENT,
        critical=DEFAULT_DISK_CRITICAL_PERCENT,
    )


__all__ = [
    "Threshold",
    "ThresholdLevel",
    "default_cpu_threshold",
    "default_disk_threshold",
    "default_memory_threshold",
]
