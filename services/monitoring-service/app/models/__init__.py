"""SQLAlchemy models for the monitoring service's 17 tables."""

from __future__ import annotations

from app.models.monitoring_audit import MonitoringAuditEntry
from app.models.monitoring_availability import MonitoringAvailability
from app.models.monitoring_collector import MonitoringCollector
from app.models.monitoring_dependency import MonitoringDependency
from app.models.monitoring_health import MonitoringHealth
from app.models.monitoring_history import MonitoringHistory
from app.models.monitoring_metric import MonitoringMetric
from app.models.monitoring_metric_series import MonitoringMetricSeries
from app.models.monitoring_report import MonitoringReport
from app.models.monitoring_retention import MonitoringRetention
from app.models.monitoring_rule import MonitoringRule
from app.models.monitoring_sla import MonitoringSLA
from app.models.monitoring_slo import MonitoringSLO
from app.models.monitoring_statistics import MonitoringStatistics
from app.models.monitoring_synthetic_test import MonitoringSyntheticTest
from app.models.monitoring_target import MonitoringTarget
from app.models.monitoring_threshold import MonitoringThreshold

__all__ = [
    "MonitoringAuditEntry",
    "MonitoringAvailability",
    "MonitoringCollector",
    "MonitoringDependency",
    "MonitoringHealth",
    "MonitoringHistory",
    "MonitoringMetric",
    "MonitoringMetricSeries",
    "MonitoringReport",
    "MonitoringRetention",
    "MonitoringRule",
    "MonitoringSLA",
    "MonitoringSLO",
    "MonitoringStatistics",
    "MonitoringSyntheticTest",
    "MonitoringTarget",
    "MonitoringThreshold",
]
