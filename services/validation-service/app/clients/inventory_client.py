"""Live lookups against the Inventory Service, backing docs/043
"INVENTORY INTEGRATION" "Integrate Prompt 036": validating Assets,
Groups, Topology (real endpoints -- see below); Labels and Dynamic
Inventory are honest platform gaps, not implemented here.

Collectors for :class:`~app.models.enums.ValidationTargetType.PHYSICAL_SERVER`/
``VIRTUAL_MACHINE``/``NETWORK_DEVICE``/etc. targets call
:meth:`get_asset` to fetch the live asset record a check's own
collected data is drawn from (status, metadata); "Topology Consistency"
checks call :meth:`get_topology`, reusing inventory-service's own real
topology endpoint since ``services/discovery-service`` exposes no
relationship endpoint of its own (see
:mod:`app.clients.discovery_client`'s own docstring).

**Honest gap**: "Label Resolution"/"Dynamic Inventory" are NOT
implemented -- ``services/inventory-service``'s own real REST surface
has no reverse "find assets by label" endpoint and no dynamic-group
membership query beyond static group membership, the same gap
``services/workflow-runtime-service``'s own
``app/clients/inventory_client.py`` already documented for an
identical reason.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx
from shared_core.exceptions.dependency import DependencyError


class InventoryClient:
    """Reads live asset/topology state from the Inventory Service."""

    def __init__(self, client: httpx.AsyncClient, *, base_url: str, caller_token: str) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._caller_token = caller_token

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._caller_token}"}

    async def get_asset(self, asset_id: UUID) -> dict[str, Any]:
        """Return *asset_id*'s own live record.

        Raises:
            DependencyError: If the Inventory Service is unreachable or
                *asset_id* does not exist.
        """
        try:
            response = await self._client.get(
                f"{self._base_url}/inventory/assets/{asset_id}", headers=self._headers()
            )
        except httpx.HTTPError as exc:
            raise DependencyError(f"Inventory Service unreachable: {exc}") from exc
        if response.status_code != httpx.codes.OK:
            raise DependencyError(
                f"Inventory Service returned HTTP {response.status_code} "
                f"reading asset {asset_id!r}."
            )
        return dict(response.json()["data"])

    async def get_topology(
        self, asset_id: UUID, *, query_kind: str = "neighbors", depth: int = 1
    ) -> dict[str, Any]:
        """Return *asset_id*'s own topology graph ("Topology Consistency").

        Raises:
            DependencyError: If the Inventory Service is unreachable or
                *asset_id* does not exist.
        """
        try:
            response = await self._client.get(
                f"{self._base_url}/inventory/topology",
                params={"asset_id": str(asset_id), "query_kind": query_kind, "depth": depth},
                headers=self._headers(),
            )
        except httpx.HTTPError as exc:
            raise DependencyError(f"Inventory Service unreachable: {exc}") from exc
        if response.status_code != httpx.codes.OK:
            raise DependencyError(
                f"Inventory Service returned HTTP {response.status_code} "
                f"reading topology for asset {asset_id!r}."
            )
        return dict(response.json()["data"])


__all__ = ["InventoryClient"]
