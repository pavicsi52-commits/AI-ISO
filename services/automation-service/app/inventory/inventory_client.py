"""Read-only lookups against ``services/inventory-service``'s own REST
API.

Per docs/040 "INVENTORY INTEGRATION" "Support": Dynamic Inventory,
Asset Groups, Labels, Tags, Topology Queries, Relationship-aware
Execution. Talks to that service's own REST API rather than its
database directly (services never share a database in this platform),
the same "lean REST client, not a generated SDK" precedent
``services/discovery-service``'s own ``InventorySyncClient`` and
``services/asset-management-service``'s own ``InventoryClient``
established.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx
from shared_core.exceptions.dependency import DependencyError


class InventoryClient:
    """Resolves inventory-service assets and asset groups for the current caller."""

    def __init__(self, client: httpx.AsyncClient, *, base_url: str) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")

    async def get_asset(self, asset_id: UUID, *, caller_token: str) -> dict[str, Any] | None:
        """Return the inventory-service asset identified by *asset_id*,
        or ``None`` if it doesn't exist.

        Raises:
            DependencyError: If the Inventory Service is unreachable or
                denies access for a reason other than "not found".
        """
        return await self._get(f"/inventory/assets/{asset_id}", caller_token=caller_token)

    async def list_group_members(
        self, group_id: UUID, *, caller_token: str
    ) -> list[dict[str, Any]]:
        """Return every asset belonging to *group_id* ("Asset Groups").

        Raises:
            DependencyError: If the Inventory Service is unreachable,
                denies access, or has no such group.
        """
        payload = await self._get(
            f"/inventory/groups/{group_id}/members", caller_token=caller_token
        )
        if payload is None:
            raise DependencyError(f"Inventory group '{group_id}' was not found.")
        members = payload.get("items", payload)
        return list(members) if isinstance(members, list) else []

    async def search_assets(self, *, query: str, caller_token: str) -> list[dict[str, Any]]:
        """Resolve a dynamic-inventory query into its matching assets
        ("Dynamic Inventory").

        Raises:
            DependencyError: If the Inventory Service is unreachable or denies access.
        """
        headers = {"Authorization": f"Bearer {caller_token}"}
        try:
            response = await self._client.get(
                f"{self._base_url}/inventory/search", headers=headers, params={"q": query}
            )
        except httpx.HTTPError as exc:
            raise DependencyError(f"Inventory Service unreachable: {exc}") from exc
        if response.status_code in (401, 403):
            raise DependencyError("Not authorized to search the Inventory Service.")
        if response.status_code != httpx.codes.OK:
            raise DependencyError(
                f"Inventory Service returned HTTP {response.status_code} searching assets."
            )
        payload = response.json()["data"]
        items = payload.get("items", payload) if isinstance(payload, dict) else payload
        return list(items) if isinstance(items, list) else []

    async def _get(self, path: str, *, caller_token: str) -> dict[str, Any] | None:
        headers = {"Authorization": f"Bearer {caller_token}"}
        try:
            response = await self._client.get(f"{self._base_url}{path}", headers=headers)
        except httpx.HTTPError as exc:
            raise DependencyError(f"Inventory Service unreachable: {exc}") from exc
        if response.status_code == httpx.codes.OK:
            data: dict[str, Any] = response.json()["data"]
            return data
        if response.status_code == httpx.codes.NOT_FOUND:
            return None
        if response.status_code in (401, 403):
            raise DependencyError("Not authorized to read this resource in the Inventory Service.")
        raise DependencyError(f"Inventory Service returned HTTP {response.status_code}.")


__all__ = ["InventoryClient"]
