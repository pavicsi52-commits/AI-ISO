"""REST API routers for the automation service."""

from __future__ import annotations

from app.api.executions import router as executions_router
from app.api.health import router as health_router
from app.api.jobs import router as jobs_router
from app.api.reports import router as reports_router
from app.api.statistics import router as statistics_router
from app.api.templates import router as templates_router

__all__ = [
    "executions_router",
    "health_router",
    "jobs_router",
    "reports_router",
    "statistics_router",
    "templates_router",
]
