"""Read-only clients for the platform services the graph syncs from.

One class rather than ten near-identical files: every call is the same
shape -- authenticated ``GET``, unwrap the ``{"data": ...}`` envelope,
raise on failure -- and only the base URL varies.

**Synchronization runs with a service token, and that is a real
departure** from ``services/dashboard-service`` and
``services/reporting-service``, which read every source as the asking
user. It has to be: a sync runs unattended at 03:00 with no user
present, so there is no caller token to forward.

The consequence is stated rather than hidden: **the graph is built with
privileged reads**, so what a node *contains* must be treated as
already-known-to-the-platform metadata -- identity, type, and
relationships -- and not as a channel for the source's own row-level
secrets. The sync mappers below therefore project a deliberately narrow
set of fields. Read access to the graph is then authorised by this
service, per organization, on every query.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
from shared_core.exceptions.dependency import DependencyError
from shared_core.exceptions.validation import ValidationError

from app.config.settings import KnowledgeGraphServiceSettings
from app.models.enums import SyncSource

_PAGE_SIZE = 500


@dataclass(frozen=True, slots=True)
class SourceEndpoints:
    """Base URLs of every platform service the graph reads."""

    inventory: str
    discovery: str
    configuration: str
    automation: str
    workflow: str
    validation: str
    monitoring: str
    alerting: str
    reporting: str
    administration: str

    def base_url_for(self, source: SyncSource) -> str:
        """Return the configured base URL for *source*.

        Raises:
            ValidationError: If the source has no configured base URL.
        """
        mapping: dict[SyncSource, str] = {
            SyncSource.INVENTORY: self.inventory,
            SyncSource.DISCOVERY: self.discovery,
            SyncSource.CONFIGURATION: self.configuration,
            SyncSource.AUTOMATION: self.automation,
            SyncSource.WORKFLOW: self.workflow,
            SyncSource.VALIDATION: self.validation,
            SyncSource.MONITORING: self.monitoring,
            SyncSource.ALERTING: self.alerting,
            SyncSource.REPORTING: self.reporting,
            SyncSource.ADMINISTRATION: self.administration,
        }
        base_url = mapping.get(source)
        if base_url is None:
            raise ValidationError(f"Sync source {str(source)!r} has no configured base URL.")
        return base_url


def build_source_endpoints(settings: KnowledgeGraphServiceSettings) -> SourceEndpoints:
    """Every sync source's base URL, in one place."""
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
        administration=settings.administration_service_base_url,
    )


def unwrap(payload: Any, result_path: str | None = None) -> list[dict[str, Any]]:
    """Extract rows from a source's response.

    Every AI-IOS service returns ``{"success": ..., "data": ...}``, so
    ``data`` is the default. A single object becomes a one-row list
    rather than being rejected: a "current state" endpoint legitimately
    returns one object.
    """
    current: Any = payload
    for part in (result_path or "data").split("."):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            current = None
            break

    if current is None:
        current = payload if isinstance(payload, list) else []
    if isinstance(current, dict):
        return [current]
    if isinstance(current, list):
        return [row for row in current if isinstance(row, dict)]
    return []


class PlatformSourceClient:
    """Authenticated read access to the platform services the graph syncs."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        endpoints: SourceEndpoints,
        *,
        service_token: str,
        page_size: int = _PAGE_SIZE,
    ) -> None:
        self._client = client
        self._endpoints = endpoints
        self._service_token = service_token
        self._page_size = page_size

    async def fetch(
        self,
        source: SyncSource,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        result_path: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch rows from one source.

        Raises:
            ValidationError: If the source is not configured.
            DependencyError: If it is unreachable or refuses the request.
        """
        base_url = self._endpoints.base_url_for(source)
        url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
        try:
            response = await self._client.get(
                url,
                params=params or {},
                headers={"Authorization": f"Bearer {self._service_token}"},
            )
        except httpx.HTTPError as exc:
            raise DependencyError(f"Source {str(source)!r} is unreachable: {exc}") from exc

        if response.status_code != httpx.codes.OK:
            raise DependencyError(
                f"Source {str(source)!r} returned HTTP {response.status_code} for {path!r}."
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise DependencyError(
                f"Source {str(source)!r} returned a non-JSON body for {path!r}."
            ) from exc
        return unwrap(payload, result_path)

    async def fetch_page(
        self,
        source: SyncSource,
        path: str,
        *,
        organization_id: str,
        since: str | None = None,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Fetch one page, optionally only what changed since a cursor.

        *since* is what makes an incremental sync incremental. A source
        that ignores the parameter simply returns everything, which the
        engine handles correctly -- it merges idempotently either way --
        but slowly.
        """
        params: dict[str, Any] = {
            "organization_id": organization_id,
            "limit": self._page_size,
            "offset": offset,
        }
        if since:
            params["updated_since"] = since
        return await self.fetch(source, path, params=params)


__all__ = [
    "PlatformSourceClient",
    "SourceEndpoints",
    "build_source_endpoints",
    "unwrap",
]
