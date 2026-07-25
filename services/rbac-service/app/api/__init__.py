"""REST API routers for the RBAC service."""

from __future__ import annotations

from app.api.authorization import router as authorization_router
from app.api.health import router as health_router
from app.api.permission import router as permission_router
from app.api.permission_group import router as permission_group_router
from app.api.policy import router as policy_router
from app.api.role import router as role_router
from app.api.user_role import router as user_role_router

__all__ = [
    "authorization_router",
    "health_router",
    "permission_group_router",
    "permission_router",
    "policy_router",
    "role_router",
    "user_role_router",
]
