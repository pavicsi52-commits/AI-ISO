"""SLA monitoring.

Per docs/023_Enterprise_Monitoring_Framework.md.txt "SLA MONITORING":
Uptime, Response Time, Availability, Error Rate, Recovery Time,
Downtime, Service Objectives, Service Level Indicators, Service Level
Agreements.
"""

from __future__ import annotations

from dataclasses import dataclass

from shared_core.monitoring.application import ApplicationStatistics
from shared_core.monitoring.availability import AvailabilityTracker
from shared_core.monitoring.constants import (
    DEFAULT_SLA_TARGET_AVAILABILITY_PERCENT,
    DEFAULT_SLA_TARGET_ERROR_RATE_PERCENT,
    DEFAULT_SLA_TARGET_RESPONSE_TIME_MS,
)


@dataclass(frozen=True, slots=True)
class ServiceLevelObjective:
    """A target this service commits to ("Service Objectives" / "SLO")."""

    target_availability_percent: float = DEFAULT_SLA_TARGET_AVAILABILITY_PERCENT
    target_response_time_ms: float = DEFAULT_SLA_TARGET_RESPONSE_TIME_MS
    target_error_rate_percent: float = DEFAULT_SLA_TARGET_ERROR_RATE_PERCENT


@dataclass(frozen=True, slots=True)
class ServiceLevelIndicators:
    """The current measured values an objective is evaluated against ("SLI")."""

    availability_percent: float
    average_response_time_ms: float
    error_rate_percent: float
    uptime_seconds: float
    downtime_seconds: float


@dataclass(frozen=True, slots=True)
class SlaReport:
    """Whether the current indicators meet the configured objective ("Service Level Agreements")."""

    objective: ServiceLevelObjective
    indicators: ServiceLevelIndicators

    @property
    def meets_availability_target(self) -> bool:
        """Whether measured availability meets or exceeds the objective."""
        return self.indicators.availability_percent >= self.objective.target_availability_percent

    @property
    def meets_response_time_target(self) -> bool:
        """Whether measured average response time is at or under the objective."""
        return self.indicators.average_response_time_ms <= self.objective.target_response_time_ms

    @property
    def meets_error_rate_target(self) -> bool:
        """Whether measured error rate is at or under the objective."""
        return self.indicators.error_rate_percent <= self.objective.target_error_rate_percent

    @property
    def meets_all_targets(self) -> bool:
        """Whether every configured target is currently being met."""
        return (
            self.meets_availability_target
            and self.meets_response_time_target
            and self.meets_error_rate_target
        )


def build_sla_report(
    *,
    objective: ServiceLevelObjective,
    statistics: ApplicationStatistics,
    availability: AvailabilityTracker,
) -> SlaReport:
    """Build an :class:`SlaReport` from the current statistics and availability tracker."""
    window = availability.current_window()
    indicators = ServiceLevelIndicators(
        availability_percent=window.percentage,
        average_response_time_ms=statistics.average_response_time_ms,
        error_rate_percent=statistics.error_rate * 100.0,
        uptime_seconds=window.up_seconds,
        downtime_seconds=window.total_seconds - window.up_seconds,
    )
    return SlaReport(objective=objective, indicators=indicators)


__all__ = ["ServiceLevelIndicators", "ServiceLevelObjective", "SlaReport", "build_sla_report"]
