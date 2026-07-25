"""REST API routers for the authentication service."""

from __future__ import annotations

from app.api.apikeys import router as apikeys_router
from app.api.auth import router as auth_router
from app.api.devices import router as devices_router
from app.api.health import router as health_router
from app.api.mfa import router as mfa_router
from app.api.password import router as password_router
from app.api.profile import router as profile_router
from app.api.sessions import router as sessions_router
from app.api.verification import router as verification_router

__all__ = [
    "apikeys_router",
    "auth_router",
    "devices_router",
    "health_router",
    "mfa_router",
    "password_router",
    "profile_router",
    "sessions_router",
    "verification_router",
]
