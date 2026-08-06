"""Router aggregation. Every router is exported here for the app factory to mount."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.analytics import router as analytics_router
from app.api.deliveries import dead_letters_router
from app.api.deliveries import router as deliveries_router
from app.api.endpoints import router as endpoints_router
from app.api.events import router as events_router
from app.api.filters import router as filters_router
from app.api.health import router as health_router
from app.api.replay import router as replay_router
from app.api.signatures import router as signatures_router
from app.api.subscriptions import router as subscriptions_router
from app.api.transformations import router as transformations_router

ALL_ROUTERS: list[APIRouter] = [
    health_router,
    endpoints_router,
    subscriptions_router,
    filters_router,
    transformations_router,
    signatures_router,
    events_router,
    deliveries_router,
    dead_letters_router,
    replay_router,
    analytics_router,
]

__all__ = ["ALL_ROUTERS"]
