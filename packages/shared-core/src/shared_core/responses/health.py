"""Health check response payloads."""

from __future__ import annotations

from shared_core.enums.health_status import HealthStatus
from shared_core.schemas.base import BaseSchema


class HealthResponse(BaseSchema):
    """Overall service health payload."""

    status: HealthStatus
    service: str
    version: str
    environment: str


class DependencyCheck(BaseSchema):
    """Result of checking a single readiness dependency."""

    name: str
    status: HealthStatus


class ReadinessResponse(BaseSchema):
    """Aggregate readiness payload."""

    status: HealthStatus
    checks: list[DependencyCheck]
