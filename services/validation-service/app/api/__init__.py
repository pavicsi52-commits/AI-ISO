"""REST API routers for the validation service."""

from __future__ import annotations

from app.api.catalog import categories_router, checks_router, rules_router
from app.api.health import router as health_router
from app.api.profiles import router as profiles_router
from app.api.remediation import router as remediation_router
from app.api.reports import router as reports_router
from app.api.results import router as results_router
from app.api.statistics import router as statistics_router
from app.api.templates import router as templates_router
from app.api.validations import router as validations_router

__all__ = [
    "categories_router",
    "checks_router",
    "health_router",
    "profiles_router",
    "remediation_router",
    "reports_router",
    "results_router",
    "rules_router",
    "statistics_router",
    "templates_router",
    "validations_router",
]
