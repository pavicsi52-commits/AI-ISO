"""The HTTP surface.

No single top-level prefix covers every router here -- ``/changes``,
``/cab``, ``/calendar``, ``/conflicts``, ``/tasks``, ``/rollback``,
``/pir``, ``/statistics``, ``/reports``, and ``/audit`` are each
distinctive nouns that do not collide, so each router owns its own
top-level path instead of being nested under a shared
``/change-management``.

**Route order is still load-bearing within a module.** FastAPI matches
in registration order, so a literal path declared after a parameterised
sibling is unreachable -- ``/reports/{report_id}`` before
``/reports/{report_id}/download`` would swallow the download route as a
malformed id. Every module here declares its literal and more-specific
paths first for that reason.
"""

from __future__ import annotations

from app.api.analytics import router as analytics_router
from app.api.cab import router as cab_router
from app.api.calendar import router as calendar_router
from app.api.changes import router as changes_router
from app.api.conflicts import router as conflicts_router
from app.api.health import router as health_router
from app.api.implementation import router as implementation_router
from app.api.pir import router as pir_router
from app.api.rollback import router as rollback_router

__all__ = [
    "analytics_router",
    "cab_router",
    "calendar_router",
    "changes_router",
    "conflicts_router",
    "health_router",
    "implementation_router",
    "pir_router",
    "rollback_router",
]
