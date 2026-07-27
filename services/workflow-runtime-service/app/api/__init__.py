"""REST API routers for the workflow runtime service."""

from __future__ import annotations

from app.api.health import router as health_router
from app.api.instances import router as instances_router
from app.api.reports import router as reports_router
from app.api.statistics import router as statistics_router
from app.api.workflows import router as workflows_router

__all__ = [
    "health_router",
    "instances_router",
    "reports_router",
    "statistics_router",
    "workflows_router",
]
