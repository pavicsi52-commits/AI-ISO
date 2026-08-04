"""The HTTP surface.

No single top-level prefix covers every router here -- ``/scheduler/jobs``,
``/scheduler/executions``, ``/scheduler/failures``, ``/scheduler/maintenance``,
``/scheduler/holidays``, ``/scheduler/priorities``, ``/scheduler/statistics``,
``/scheduler/reports``, and ``/scheduler/audit`` are each distinctive nouns
under the shared ``/scheduler`` namespace docs/054's own REST API section
uses, rather than one router owning every path.

**Route order is still load-bearing within a module.** FastAPI matches
in registration order, so a literal path declared after a parameterised
sibling is unreachable -- ``/scheduler/maintenance/active`` before
``/scheduler/maintenance/{window_id}`` would otherwise be swallowed as a
malformed id. Every module here declares its literal and more-specific
paths first for that reason.
"""

from __future__ import annotations

from app.api.analytics import router as analytics_router
from app.api.executions import router as executions_router
from app.api.failures import router as failures_router
from app.api.health import router as health_router
from app.api.holidays import router as holidays_router
from app.api.jobs import router as jobs_router
from app.api.maintenance import router as maintenance_router
from app.api.priorities import router as priorities_router

__all__ = [
    "analytics_router",
    "executions_router",
    "failures_router",
    "health_router",
    "holidays_router",
    "jobs_router",
    "maintenance_router",
    "priorities_router",
]
