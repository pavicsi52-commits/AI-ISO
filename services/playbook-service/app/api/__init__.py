"""REST API routers for the playbook service."""

from __future__ import annotations

from app.api.health import router as health_router
from app.api.playbooks import router as playbooks_router
from app.api.reports import router as reports_router
from app.api.repository_folders import router as repository_folders_router
from app.api.search import router as search_router
from app.api.statistics import router as statistics_router
from app.api.templates import router as templates_router

__all__ = [
    "health_router",
    "playbooks_router",
    "reports_router",
    "repository_folders_router",
    "search_router",
    "statistics_router",
    "templates_router",
]
