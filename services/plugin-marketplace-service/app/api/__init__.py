"""Router aggregation. Every router is exported here for the app factory to mount."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.health import router as health_router
from app.api.installations import router as installations_router
from app.api.marketplace import router as marketplace_admin_router
from app.api.packages import router as packages_router
from app.api.plugins import router as plugins_router
from app.api.publishers import router as publishers_router

ALL_ROUTERS: list[APIRouter] = [
    health_router,
    # Every router with a static path segment under "/plugins/..." must be
    # registered before ``plugins_router``: FastAPI/Starlette matches
    # routes in registration order, and ``plugins_router`` owns the
    # catch-all ``GET /plugins/{plugin_id}`` (plus ``PUT``/``DELETE`` at
    # that same one-segment shape). Registered first, that catch-all
    # would hijack same-arity static paths like ``GET /plugins/publishers``
    # -- matching them as ``plugin_id="publishers"`` and failing UUID
    # parsing -- before the request ever reaches the router that actually
    # owns the path. The same router-ordering bug class already found and
    # fixed in notification-center-service.
    publishers_router,
    installations_router,
    packages_router,
    marketplace_admin_router,
    plugins_router,
]

__all__ = ["ALL_ROUTERS"]
