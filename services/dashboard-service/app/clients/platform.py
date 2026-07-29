"""Read-only clients for every platform service dashboard widgets draw from
("DATA SOURCES").

One class rather than twelve near-identical files: every call is the
same shape -- authenticated ``GET``, unwrap the ``{"data": ...}``
envelope, raise on failure -- and only the base URL varies.

**Every call carries the caller's own bearer token**, never a service
credential. A dashboard therefore cannot show data the viewing user could
not have fetched themselves, which keeps RBAC enforced by the
service that owns the data instead of reimplemented here. A 403 from a
source is the correct outcome, not a bug.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx
from shared_core.exceptions.dependency import DependencyError
from shared_core.exceptions.validation import ValidationError

from app.config.settings import DashboardServiceSettings
from app.models.enums import DataSource

_ALLOWED_CUSTOM_SCHEMES = frozenset({"http", "https"})


@dataclass(frozen=True, slots=True)
class SourceEndpoints:
    """Base URLs of every platform service this service reads."""

    inventory: str
    discovery: str
    configuration: str
    automation: str
    workflow: str
    validation: str
    monitoring: str
    alerting: str
    reporting: str
    ai_assistant: str
    compliance: str
    incident: str
    administration: str

    def base_url_for(self, source: DataSource) -> str:
        """Return the configured base URL for *source*.

        Raises:
            ValidationError: If *source* is not fetched over HTTP. Three
                members legitimately are not: ``CUSTOM_API`` carries its
                own absolute URL, ``STATIC`` needs no fetch at all, and
                ``TOPOLOGY`` is read from Neo4j by
                :class:`~app.topology.graph.TopologyReader`. Each gets
                its own message, because "no configured base URL" told
                an author nothing about which of the three they hit.
        """
        mapping: dict[DataSource, str] = {
            DataSource.INVENTORY: self.inventory,
            DataSource.DISCOVERY: self.discovery,
            DataSource.CONFIGURATION: self.configuration,
            DataSource.AUTOMATION: self.automation,
            DataSource.WORKFLOW: self.workflow,
            DataSource.VALIDATION: self.validation,
            DataSource.MONITORING: self.monitoring,
            DataSource.ALERTING: self.alerting,
            DataSource.REPORTING: self.reporting,
            DataSource.AI_ASSISTANT: self.ai_assistant,
            DataSource.COMPLIANCE: self.compliance,
            DataSource.INCIDENT: self.incident,
            DataSource.ADMINISTRATION: self.administration,
        }
        base_url = mapping.get(source)
        if base_url is not None:
            return base_url
        if source is DataSource.CUSTOM_API:
            raise ValidationError("A custom_api query must supply an absolute URL in its path.")
        if source is DataSource.TOPOLOGY:
            raise ValidationError(
                "The 'topology' data source is read from the graph, not over HTTP; "
                "use it only on a topology_graph widget."
            )
        raise ValidationError(
            f"Data source {str(source)!r} is not fetched over HTTP and has no base URL."
        )


def build_source_endpoints(settings: DashboardServiceSettings) -> SourceEndpoints:
    """Every data source's base URL, in one place.

    Lives here rather than in the application factory so the API
    dependencies and any worker read the same mapping -- two copies of
    twelve base URLs is two places to forget one.
    """
    return SourceEndpoints(
        inventory=settings.inventory_service_base_url,
        discovery=settings.discovery_service_base_url,
        configuration=settings.configuration_service_base_url,
        automation=settings.automation_service_base_url,
        workflow=settings.workflow_runtime_service_base_url,
        validation=settings.validation_service_base_url,
        monitoring=settings.monitoring_service_base_url,
        alerting=settings.alerting_service_base_url,
        reporting=settings.reporting_service_base_url,
        ai_assistant=settings.ai_assistant_service_base_url,
        compliance=settings.compliance_service_base_url,
        incident=settings.incident_service_base_url,
        administration=settings.administration_service_base_url,
    )


def unwrap(payload: Any, result_path: str | None) -> list[dict[str, Any]]:
    """Extract rows from a source's response.

    Every AI-IOS service returns ``{"success": ..., "data": ...}``, so
    ``data`` is the default. ``result_path`` handles nesting and
    third-party shapes.

    A single object is wrapped into a one-row list rather than rejected:
    a "current statistics" endpoint legitimately returns one object, and
    a metric card should be able to read it.
    """
    current: Any = payload
    path = result_path or "data"
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            current = None
            break

    if current is None:
        # Some endpoints are already the bare list.
        current = payload if isinstance(payload, list) else []
    if isinstance(current, dict):
        return [current]
    if isinstance(current, list):
        return [row if isinstance(row, dict) else {"value": row} for row in current]
    return [{"value": current}]


class PlatformSourceClient:
    """Authenticated read access to platform data sources."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        endpoints: SourceEndpoints,
        *,
        caller_token: str,
        max_rows: int = 50_000,
    ) -> None:
        self._client = client
        self._endpoints = endpoints
        self._caller_token = caller_token
        self._max_rows = max_rows

    def _resolve_url(self, source: DataSource, path: str) -> str:
        """Build the absolute URL for one query.

        A ``custom_api`` path must itself be an absolute ``http(s)``
        URL. Anything else -- a ``file://`` URL, a bare path, a scheme
        this service does not speak -- is refused rather than handed to
        the HTTP client, because a template is user-authored content and
        must not be able to point the service at arbitrary schemes.
        """
        if source is DataSource.CUSTOM_API:
            parsed = urlparse(path)
            if parsed.scheme not in _ALLOWED_CUSTOM_SCHEMES or not parsed.netloc:
                raise ValidationError(
                    "A custom_api query requires an absolute http(s) URL; " f"got {path!r}."
                )
            return path
        return f"{self._endpoints.base_url_for(source).rstrip('/')}/{path.lstrip('/')}"

    async def fetch(
        self,
        source: DataSource,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        result_path: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch rows from one data source.

        Raises:
            ValidationError: If the query is malformed.
            DependencyError: If the source is unreachable, refuses the
                request, or returns more rows than the configured
                ceiling allows.
        """
        url = self._resolve_url(source, path)
        try:
            response = await self._client.get(
                url,
                params=params or {},
                headers={"Authorization": f"Bearer {self._caller_token}"},
            )
        except httpx.HTTPError as exc:
            raise DependencyError(f"Data source {str(source)!r} is unreachable: {exc}") from exc

        if response.status_code != httpx.codes.OK:
            raise DependencyError(
                f"Data source {str(source)!r} returned HTTP {response.status_code} for {path!r}."
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise DependencyError(
                f"Data source {str(source)!r} returned a non-JSON body for {path!r}."
            ) from exc

        rows = unwrap(payload, result_path)
        if len(rows) > self._max_rows:
            raise DependencyError(
                f"Data source {str(source)!r} returned {len(rows):,} rows for {path!r}, "
                f"above the {self._max_rows:,}-row ceiling. Narrow the report's filters "
                "or raise AIIOS_DASHBOARD_SERVICE_MAX_ROWS_PER_WIDGET."
            )
        return rows


__all__ = ["PlatformSourceClient", "SourceEndpoints", "build_source_endpoints", "unwrap"]
