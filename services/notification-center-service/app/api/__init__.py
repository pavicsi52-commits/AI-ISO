"""Every router this service mounts.

**No single top-level prefix covers every router** -- ``/health``,
``/liveness``, and ``/readiness`` sit at the root (per docs/008, every
service exposes these unprefixed), while every business route sits
under ``/notifications`` or one of its own sub-paths
(``/notifications/preferences``, ``/notifications/templates``,
``/notifications/subscriptions``, ``/notifications/channels``,
``/notifications/announcements``, ``/notifications/dead-letters``),
mirroring the same "one shared business namespace, several routers
beneath it" shape every prior AI-IOS service already establishes.
"""

from __future__ import annotations

from app.api.analytics import router as analytics_router
from app.api.announcements import router as announcements_router
from app.api.channels import router as channels_router
from app.api.deliveries import router as deliveries_router
from app.api.health import router as health_router
from app.api.notifications import router as notifications_router
from app.api.preferences import router as preferences_router
from app.api.subscriptions import router as subscriptions_router
from app.api.templates import router as templates_router

__all__ = [
    "analytics_router",
    "announcements_router",
    "channels_router",
    "deliveries_router",
    "health_router",
    "notifications_router",
    "preferences_router",
    "subscriptions_router",
    "templates_router",
]
