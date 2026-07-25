"""REST API routers for the project service."""

from __future__ import annotations

from app.api.export import router as export_router
from app.api.health import router as health_router
from app.api.import_ import router as import_router
from app.api.project import router as project_router
from app.api.project_analytics import router as project_analytics_router
from app.api.project_member import router as project_member_router
from app.api.project_settings import router as project_settings_router
from app.api.project_template import router as project_template_router
from app.api.search import router as search_router

__all__ = [
    "export_router",
    "health_router",
    "import_router",
    "project_analytics_router",
    "project_member_router",
    "project_router",
    "project_settings_router",
    "project_template_router",
    "search_router",
]
