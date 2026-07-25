"""Read-only lookups against ``services/inventory-service``'s own REST
API.

Per docs/038's own framing ("Inventory identifies assets. Asset
Management manages assets."), this service correlates every
:class:`~app.models.managed_asset.ManagedAsset` against an
``inventory-service`` asset via ``inventory_asset_id`` -- this client
confirms that asset genuinely exists (and belongs to the calling
organization) before this service agrees to govern it. Talks to that
service's own REST API rather than its database directly (services
never share a database in this platform), the same "lean REST client,
not a generated SDK" precedent ``services/discovery-service``'s own
``InventorySyncClient`` established.
"""

from __future__ import annotations

from uuid import UUID

import httpx
from shared_core.exceptions.dependency import DependencyError


class InventoryClient:
    """Looks up inventory-service assets for the current caller."""

    def __init__(self, client: httpx.AsyncClient, *, base_url: str) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")

    async def get_asset_summary(
        self, inventory_asset_id: UUID, *, caller_token: str
    ) -> dict[str, object] | None:
        """Return the inventory-service asset identified by
        *inventory_asset_id*, or ``None`` if it doesn't exist.

        Raises:
            DependencyError: If the Inventory Service is unreachable or
                denies access for a reason other than "not found".
        """
        headers = {"Authorization": f"Bearer {caller_token}"}
        try:
            response = await self._client.get(
                f"{self._base_url}/inventory/assets/{inventory_asset_id}", headers=headers
            )
        except httpx.HTTPError as exc:
            raise DependencyError(f"Inventory Service unreachable: {exc}") from exc

        if response.status_code == httpx.codes.OK:
            data: dict[str, object] = response.json()["data"]
            return data
        if response.status_code == httpx.codes.NOT_FOUND:
            return None
        if response.status_code in (401, 403):
            raise DependencyError("Not authorized to read this asset in the Inventory Service.")
        raise DependencyError(
            f"Inventory Service returned HTTP {response.status_code} fetching an asset."
        )


__all__ = ["InventoryClient"]
