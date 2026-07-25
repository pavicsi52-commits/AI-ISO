"""REST API routers for the secrets management service."""

from __future__ import annotations

from app.api.api_key import router as api_key_router
from app.api.certificate import router as certificate_router
from app.api.health import router as health_router
from app.api.lease import router as lease_router
from app.api.provider import router as provider_router
from app.api.search import router as search_router
from app.api.secret import router as secret_router
from app.api.ssh_key import router as ssh_key_router

__all__ = [
    "api_key_router",
    "certificate_router",
    "health_router",
    "lease_router",
    "provider_router",
    "search_router",
    "secret_router",
    "ssh_key_router",
]
