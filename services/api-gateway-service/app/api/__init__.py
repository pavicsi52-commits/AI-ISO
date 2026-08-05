"""Router aggregation.

Every management router is exported here for the app factory to mount.
``proxy_router`` is deliberately **not** included in :data:`MANAGEMENT_ROUTERS`
-- it matches every path and method and must be mounted by the factory
strictly last, after every router below, or it swallows them all.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.analytics import router as analytics_router
from app.api.apikeys import router as apikeys_router
from app.api.clients import router as clients_router
from app.api.gateway_health import router as gateway_health_router
from app.api.graphql_router import router as graphql_router
from app.api.health import router as health_router
from app.api.openapi import router as openapi_router
from app.api.policies import quotas_router, rate_limits_router
from app.api.proxy import router as proxy_router
from app.api.routes import router as routes_router
from app.api.services import router as services_router
from app.api.transformations import router as transformations_router
from app.api.websocket_router import router as websocket_router

MANAGEMENT_ROUTERS: list[APIRouter] = [
    health_router,
    services_router,
    routes_router,
    clients_router,
    apikeys_router,
    rate_limits_router,
    quotas_router,
    transformations_router,
    gateway_health_router,
    analytics_router,
    openapi_router,
    graphql_router,
    websocket_router,
]

__all__ = ["MANAGEMENT_ROUTERS", "proxy_router"]
