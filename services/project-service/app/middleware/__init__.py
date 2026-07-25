"""ASGI middleware for the project service."""

from __future__ import annotations

from app.middleware.timing import TimingMiddleware

__all__ = ["TimingMiddleware"]
