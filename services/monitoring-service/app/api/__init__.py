"""REST API routers for the monitoring service."""

from __future__ import annotations

from app.api.health import router as health_router
from app.api.monitoring_availability import router as availability_router
from app.api.monitoring_collectors import router as collectors_router
from app.api.monitoring_dependencies import router as dependencies_router
from app.api.monitoring_health import router as monitoring_health_router
from app.api.monitoring_history import router as history_router
from app.api.monitoring_metrics import router as metrics_router
from app.api.monitoring_performance import router as performance_router
from app.api.monitoring_reports import router as reports_router
from app.api.monitoring_retention import router as retention_router
from app.api.monitoring_rules import router as rules_router
from app.api.monitoring_sla import router as sla_router
from app.api.monitoring_slo import router as slo_router
from app.api.monitoring_statistics import router as statistics_router
from app.api.monitoring_synthetic_tests import router as synthetic_tests_router
from app.api.monitoring_targets import router as targets_router
from app.api.monitoring_thresholds import router as thresholds_router

__all__ = [
    "availability_router",
    "collectors_router",
    "dependencies_router",
    "health_router",
    "history_router",
    "metrics_router",
    "monitoring_health_router",
    "performance_router",
    "reports_router",
    "retention_router",
    "rules_router",
    "sla_router",
    "slo_router",
    "statistics_router",
    "synthetic_tests_router",
    "targets_router",
    "thresholds_router",
]
