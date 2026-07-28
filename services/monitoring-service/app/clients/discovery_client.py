"""Live lookups against the Discovery Service, backing docs/044
"INTEGRATIONS": "Discovery (Prompt 037)" -- reading a discovery job's
own summary so newly discovered assets can be considered for
auto-registration as :class:`~app.models.monitoring_target
.MonitoringTarget` rows ("Dynamic Inventory", "Collector Auto-
discovery").

**Honest gap**: ``DiscoveryRelationshipService``/
``DiscoveryRelationshipRepository`` exist internally in
``services/discovery-service`` but no REST router exposes them, the
same gap ``services/validation-service``'s own
:mod:`app.clients.discovery_client` already documented -- topology/
relationship data for "Topology-aware Health" is read from
``services/inventory-service``'s own real ``/inventory/topology``
endpoint instead (see :mod:`app.clients.inventory_client`).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx
from shared_core.exceptions.dependency import DependencyError


class DiscoveryClient:
    """Reads discovery job summaries from the Discovery Service."""

    def __init__(self, client: httpx.AsyncClient, *, base_url: str, caller_token: str) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._caller_token = caller_token

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._caller_token}"}

    async def get_job(self, job_id: UUID) -> dict[str, Any]:
        """Return *job_id*'s own discovery job summary.

        Raises:
            DependencyError: If the Discovery Service is unreachable or
                *job_id* does not exist.
        """
        try:
            response = await self._client.get(
                f"{self._base_url}/discovery/jobs/{job_id}", headers=self._headers()
            )
        except httpx.HTTPError as exc:
            raise DependencyError(f"Discovery Service unreachable: {exc}") from exc
        if response.status_code != httpx.codes.OK:
            raise DependencyError(
                f"Discovery Service returned HTTP {response.status_code} "
                f"reading job {job_id!r}."
            )
        return dict(response.json()["data"])


__all__ = ["DiscoveryClient"]
