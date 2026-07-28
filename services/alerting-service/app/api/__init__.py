"""Every alerting service API router."""

from __future__ import annotations

from app.api.alert_analytics import reports_router, statistics_router
from app.api.alert_configuration import (
    escalation_router,
    routes_router,
    suppression_router,
)
from app.api.alert_rules import router as rules_router
from app.api.alerts import router as alerts_router
from app.api.health import router as health_router
from app.api.maintenance_windows import router as maintenance_windows_router
from app.api.oncall_schedules import router as oncall_schedules_router

__all__ = [
    "alerts_router",
    "escalation_router",
    "health_router",
    "maintenance_windows_router",
    "oncall_schedules_router",
    "reports_router",
    "routes_router",
    "rules_router",
    "statistics_router",
    "suppression_router",
]
