"""Live lookups against the Discovery Service, backing docs/043
"DISCOVERY INTEGRATION" "Integrate Prompt 037": validating Discovered
Assets and Discovery Accuracy at a job-summary level.

**Honest gap**: "Relationship Integrity"/"Topology Consistency" are NOT
implemented against ``services/discovery-service`` itself --
``DiscoveryRelationshipService``/``DiscoveryRelationshipRepository``
exist internally there but no REST router exposes them
(``app/core/factory.py`` registers no ``relationship_router``), so
there is nothing this client could call. Topology/relationship checks
instead read ``services/inventory-service``'s own real
``/inventory/topology`` endpoint (see
:meth:`app.clients.inventory_client.InventoryClient.get_topology`),
under the reasonable assumption that inventory-service is the system
of record discovery ultimately writes into.
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
        """Return *job_id*'s own discovery job summary ("Discovery Accuracy").

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
