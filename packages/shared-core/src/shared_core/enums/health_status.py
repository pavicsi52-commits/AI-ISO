"""Health check status enumeration."""

from enum import StrEnum


class HealthStatus(StrEnum):
    """Overall health of a service or dependency.

    Six values per docs/023_Enterprise_Monitoring_Framework.md.txt
    "SERVICE STATUS" ("Healthy, Degraded, Warning, Unavailable,
    Maintenance, Unknown"). The Prompt 012 baseline's four values
    (``HEALTHY``/``DEGRADED``/``UNHEALTHY``/``UNKNOWN``) already have 14
    call sites across ``database``/``cache``/``events``/``queue``/
    ``monitoring``, so ``UNHEALTHY`` was kept rather than renamed to
    "Unavailable" (the spec's term for the same concept) -- ``WARNING``
    and ``MAINTENANCE`` are additive.
    """

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    WARNING = "warning"
    UNHEALTHY = "unhealthy"
    MAINTENANCE = "maintenance"
    UNKNOWN = "unknown"
