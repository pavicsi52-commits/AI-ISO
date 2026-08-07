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
    plugins_router,
    installations_router,
    packages_router,
    publishers_router,
    marketplace_admin_router,
]

__all__ = ["ALL_ROUTERS"]
