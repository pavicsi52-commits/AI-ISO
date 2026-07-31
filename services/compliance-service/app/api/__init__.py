"""The HTTP surface.

**Router order is load-bearing**, and so is route order inside each
module. All four business routers mount under ``/compliance``, and each
has literal segments -- ``/compliance/findings/summary``,
``/compliance/exceptions/expiring``, ``/compliance/scores/history`` --
sitting alongside parameterised siblings like
``/compliance/findings/{finding_id}``.

FastAPI matches in registration order, so a literal route declared after
its parameterised sibling is unreachable: the request is parsed as a
finding whose id is the word "summary" and answers 422 for a malformed
UUID. Every module here declares its literal paths before its
parameterised ones for that reason.
"""

from __future__ import annotations

from app.api.analytics import router as analytics_router
from app.api.assessments import router as assessments_router
from app.api.catalogue import router as catalogue_router
from app.api.governance import router as governance_router
from app.api.health import router as health_router

__all__ = [
    "analytics_router",
    "assessments_router",
    "catalogue_router",
    "governance_router",
    "health_router",
]
