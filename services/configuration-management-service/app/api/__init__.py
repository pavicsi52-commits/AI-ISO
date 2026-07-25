"""REST API routers for the configuration management service."""

from __future__ import annotations

from app.api.analytics import router as analytics_router
from app.api.compliance import router as compliance_router
from app.api.drift import router as drift_router
from app.api.git import router as git_router
from app.api.health import router as health_router
from app.api.profile import router as profile_router
from app.api.report import router as report_router
from app.api.template import router as template_router

__all__ = [
    "analytics_router",
    "compliance_router",
    "drift_router",
    "git_router",
    "health_router",
    "profile_router",
    "report_router",
    "template_router",
]
