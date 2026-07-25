"""ASGI middleware for the user management service."""

from __future__ import annotations

from app.middleware.timing import TimingMiddleware

__all__ = ["TimingMiddleware"]
