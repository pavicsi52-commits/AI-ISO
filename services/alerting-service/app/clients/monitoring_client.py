"""Live lookups against the Monitoring Service, backing docs/045
"ALERT SOURCES": Monitoring, and "CORRELATION" "Support":
Topology Correlation, Dependency Correlation.

Reads ``services/monitoring-service``'s own real endpoints
(``GET /monitoring/health``, ``GET /monitoring-dependencies``) --
verified against that service's own routers, not assumed from its own
prompt doc.

:meth:`list_dependency_children` is what a genuine topology-aware
correlation pass would consume: given the target an alert names, it
returns every target that depends on it, i.e. the blast radius whose
own alerts are downstream symptoms rather than independent causes. See
:mod:`app.correlation.engine`'s own docstring for the honest note on
why the scheduler-driven correlation pass cannot currently call this
(no service-account credential mechanism exists platform-wide yet) and
falls back to shared-reference correlation instead.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx
from shared_core.exceptions.dependency import DependencyError


class MonitoringClient:
    """Reads live health and dependency-graph state from the Monitoring Service."""

    def __init__(self, client: httpx.AsyncClient, *, base_url: str, caller_token: str) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._caller_token = caller_token

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._caller_token}"}

    async def list_health_for_target(self, target_id: UUID) -> list[dict[str, Any]]:
        """Every health-check result recorded for *target_id*.

        Raises:
            DependencyError: If the Monitoring Service is unreachable.
        """
        try:
            response = await self._client.get(
                f"{self._base_url}/monitoring/health",
                params={"target_id": str(target_id)},
                headers=self._headers(),
            )
        except httpx.HTTPError as exc:
            raise DependencyError(f"Monitoring Service unreachable: {exc}") from exc
        if response.status_code != httpx.codes.OK:
            raise DependencyError(
                f"Monitoring Service returned HTTP {response.status_code} "
                f"reading health for target {target_id!r}."
            )
        return list(response.json()["data"])

    async def list_dependency_children(self, parent_target_id: UUID) -> list[dict[str, Any]]:
        """Every target that depends on *parent_target_id* ("Blast Radius").

        Raises:
            DependencyError: If the Monitoring Service is unreachable.
        """
        try:
            response = await self._client.get(
                f"{self._base_url}/monitoring-dependencies",
                params={"parent_target_id": str(parent_target_id)},
                headers=self._headers(),
            )
        except httpx.HTTPError as exc:
            raise DependencyError(f"Monitoring Service unreachable: {exc}") from exc
        if response.status_code != httpx.codes.OK:
            raise DependencyError(
                f"Monitoring Service returned HTTP {response.status_code} "
                f"reading dependencies for target {parent_target_id!r}."
            )
        return list(response.json()["data"])


__all__ = ["MonitoringClient"]
