"""Router aggregation. Every router is exported here for the app factory to mount."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.analytics import router as analytics_router
from app.api.connectors import categories_router
from app.api.connectors import router as connectors_router
from app.api.credentials import router as credentials_router
from app.api.events import router as events_router
from app.api.flows import router as flows_router
from app.api.health import router as health_router
from app.api.marketplace import router as marketplace_router
from app.api.transformations import router as transformations_router

ALL_ROUTERS: list[APIRouter] = [
    health_router,
    connectors_router,
    categories_router,
    credentials_router,
    transformations_router,
    flows_router,
    events_router,
    marketplace_router,
    analytics_router,
]

__all__ = ["ALL_ROUTERS"]
