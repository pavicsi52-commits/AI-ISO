"""ASGI middleware for the authentication service."""

from __future__ import annotations

from app.middleware.timing import TimingMiddleware

__all__ = ["TimingMiddleware"]
