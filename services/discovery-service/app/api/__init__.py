"""REST API routers for the discovery service."""

from __future__ import annotations

from app.api.health import router as health_router
from app.api.job import router as job_router
from app.api.profile import router as profile_router
from app.api.result import router as result_router
from app.api.scan import router as scan_router
from app.api.schedule import router as schedule_router
from app.api.statistics import router as statistics_router

__all__ = [
    "health_router",
    "job_router",
    "profile_router",
    "result_router",
    "scan_router",
    "schedule_router",
    "statistics_router",
]
