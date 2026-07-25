"""Dashboard support.

Per docs/023_Enterprise_Monitoring_Framework.md.txt "DASHBOARD SUPPORT":
"Provide reusable APIs for" Grafana, OpenSearch Dashboards, Native
AI-IOS Dashboard, Custom Dashboards. Deliberately data-shaping only
("DO NOT IMPLEMENT": Grafana Server, Prometheus Server) -- Grafana's
own need is already met by this package's registered Prometheus
metrics (scraped externally; nothing extra to build here). This module
is what shapes a point-in-time monitoring snapshot into a plain,
JSON-serializable dict any other dashboard consumer can render:
OpenSearch Dashboards indexes/visualizes it automatically once emitted
as a structured log line through :mod:`shared_core.logging`, and the
future native AI-IOS dashboard (or any custom one) can serve it directly
as an API response.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from shared_core.enums.health_status import HealthStatus
from shared_core.monitoring.application import ApplicationSnapshot
from shared_core.monitoring.availability import AvailabilityWindow
from shared_core.monitoring.checks import DependencyCheckResult
from shared_core.monitoring.resources import ResourceSnapshot


def build_dashboard_payload(
    *,
    service_name: str,
    status: HealthStatus,
    application: ApplicationSnapshot,
    resources: ResourceSnapshot,
    dependencies: list[DependencyCheckResult],
    availability: AvailabilityWindow,
) -> dict[str, Any]:
    """Shape a full monitoring snapshot into one plain, JSON-serializable dict."""
    return {
        "service": service_name,
        "status": status.value,
        "timestamp": datetime.now(UTC).isoformat(),
        "application": asdict(application),
        "resources": asdict(resources),
        "dependencies": [asdict(dependency) for dependency in dependencies],
        "availability": asdict(availability),
    }


__all__ = ["build_dashboard_payload"]
