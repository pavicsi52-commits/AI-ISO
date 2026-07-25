"""REST API routers for the inventory service."""

from __future__ import annotations

from app.api.analytics import router as analytics_router
from app.api.asset import router as asset_router
from app.api.export import router as export_router
from app.api.group import router as group_router
from app.api.health import router as health_router
from app.api.import_ import router as import_router
from app.api.relationship import router as relationship_router
from app.api.search import router as search_router
from app.api.statistics import router as statistics_router
from app.api.topology import router as topology_router

__all__ = [
    "analytics_router",
    "asset_router",
    "export_router",
    "group_router",
    "health_router",
    "import_router",
    "relationship_router",
    "search_router",
    "statistics_router",
    "topology_router",
]
