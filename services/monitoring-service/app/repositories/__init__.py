"""Repositories for the monitoring service's 17 tables."""

from __future__ import annotations

from app.repositories.monitoring_audit import MonitoringAuditEntryRepository
from app.repositories.monitoring_availability import MonitoringAvailabilityRepository
from app.repositories.monitoring_collector import MonitoringCollectorRepository
from app.repositories.monitoring_dependency import MonitoringDependencyRepository
from app.repositories.monitoring_health import MonitoringHealthRepository
from app.repositories.monitoring_history import MonitoringHistoryRepository
from app.repositories.monitoring_metric import MonitoringMetricRepository
from app.repositories.monitoring_metric_series import MonitoringMetricSeriesRepository
from app.repositories.monitoring_report import MonitoringReportRepository
from app.repositories.monitoring_retention import MonitoringRetentionRepository
from app.repositories.monitoring_rule import MonitoringRuleRepository
from app.repositories.monitoring_sla import MonitoringSLARepository
from app.repositories.monitoring_slo import MonitoringSLORepository
from app.repositories.monitoring_statistics import MonitoringStatisticsRepository
from app.repositories.monitoring_synthetic_test import MonitoringSyntheticTestRepository
from app.repositories.monitoring_target import MonitoringTargetRepository
from app.repositories.monitoring_threshold import MonitoringThresholdRepository

__all__ = [
    "MonitoringAuditEntryRepository",
    "MonitoringAvailabilityRepository",
    "MonitoringCollectorRepository",
    "MonitoringDependencyRepository",
    "MonitoringHealthRepository",
    "MonitoringHistoryRepository",
    "MonitoringMetricRepository",
    "MonitoringMetricSeriesRepository",
    "MonitoringReportRepository",
    "MonitoringRetentionRepository",
    "MonitoringRuleRepository",
    "MonitoringSLARepository",
    "MonitoringSLORepository",
    "MonitoringStatisticsRepository",
    "MonitoringSyntheticTestRepository",
    "MonitoringTargetRepository",
    "MonitoringThresholdRepository",
]
