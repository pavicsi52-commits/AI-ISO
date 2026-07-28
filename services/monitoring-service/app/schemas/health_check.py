"""Request/response schemas for ``GET /monitoring/health``.

Named ``health_check.py``, not ``health.py``, to avoid colliding with
the platform-wide ``app/schemas/health.py`` (the generic
``/health``/``/readiness``/``/liveness`` envelope every AI-IOS service
exposes) -- this module is about a *target's own* monitored health
result, an unrelated concept that happens to share the English word
"health".
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel
from shared_core.enums.health_status import HealthStatus

from app.models.enums import HealthCheckType


class MonitoringHealthResponse(BaseModel):
    """One health-check result snapshot for a target."""

    id: UUID
    organization_id: UUID
    target_id: UUID
    check_type: HealthCheckType
    status: HealthStatus
    message: str | None
    checked_at: datetime


__all__ = ["MonitoringHealthResponse"]
