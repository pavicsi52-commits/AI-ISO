"""The HTTP surface.

Unlike prior services, no single top-level prefix covers every router
here -- ``/incidents``, ``/major-incidents``, ``/war-rooms``,
``/postmortems``, ``/problems``, ``/known-errors``, ``/root-cause``,
``/statistics``, ``/reports``, and ``/audit`` are each distinctive nouns
that do not collide, so each router owns its own top-level path instead
of being nested under a shared ``/incident-management``.

**Route order is still load-bearing within a module.** FastAPI matches
in registration order, so a literal path declared after a parameterised
sibling is unreachable -- ``/reports/{report_id}`` before
``/reports/{report_id}/download`` would swallow the download route as a
malformed id. Every module here declares its literal and more-specific
paths first for that reason.
"""

from __future__ import annotations

from app.api.analytics import router as analytics_router
from app.api.health import router as health_router
from app.api.incidents import router as incidents_router
from app.api.major import router as major_incidents_router
from app.api.major import war_room_router
from app.api.postmortem import router as postmortem_router
from app.api.rca import router as rca_router

__all__ = [
    "analytics_router",
    "health_router",
    "incidents_router",
    "major_incidents_router",
    "postmortem_router",
    "rca_router",
    "war_room_router",
]
