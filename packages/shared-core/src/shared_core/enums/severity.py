"""Severity level enumeration."""

from enum import StrEnum


class Severity(StrEnum):
    """Severity used by validation, alerting, and logging."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"
