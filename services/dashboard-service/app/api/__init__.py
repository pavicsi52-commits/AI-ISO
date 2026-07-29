"""HTTP routers for the dashboard service.

**Include order matters.** docs/048 specifies both ``/dashboards/{id}``
and literal collections like ``/dashboards/templates``,
``/dashboards/statistics``, and ``/dashboards/share``. FastAPI matches
routes in registration order, so the routers owning literal segments
must be included *before* :data:`dashboards_router`; otherwise
``/dashboards/statistics`` would be parsed as a dashboard whose id is
the word "statistics" and 422 forever.
"""

from __future__ import annotations

from app.api.analytics import router as analytics_router
from app.api.catalog import router as catalog_router
from app.api.dashboards import router as dashboards_router
from app.api.health import router as health_router
from app.api.sharing import router as sharing_router

__all__ = [
    "analytics_router",
    "catalog_router",
    "dashboards_router",
    "health_router",
    "sharing_router",
]
