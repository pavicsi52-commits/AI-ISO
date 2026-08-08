"""Router aggregation. Every router is exported here for the app factory to mount."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.agents import router as agents_router
from app.api.health import router as health_router

ALL_ROUTERS: list[APIRouter] = [
    health_router,
    agents_router,
]

__all__ = ["ALL_ROUTERS"]
