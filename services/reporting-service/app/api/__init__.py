"""API routers for the Reporting Service."""

from __future__ import annotations

from app.api.delivery import router as delivery_router
from app.api.health import router as health_router
from app.api.reports import router as reports_router
from app.api.templates import router as templates_router

__all__ = ["delivery_router", "health_router", "reports_router", "templates_router"]
