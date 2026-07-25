"""ASGI middleware for the secrets management service."""

from __future__ import annotations

from app.middleware.timing import TimingMiddleware

__all__ = ["TimingMiddleware"]
