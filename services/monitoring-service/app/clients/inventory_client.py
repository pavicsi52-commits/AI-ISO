"""Live lookups against the Inventory Service, backing docs/044
"MONITORING TARGETS" "Support": Physical Servers/Virtual Machines/
Network Devices/etc. as monitored targets, and "Dynamic Inventory"
(reusing the same real ``GET /inventory/assets/{id}`` this platform's
own ``services/validation-service``'s own
:mod:`app.clients.inventory_client` already established for the
identical Inventory Service).

:meth:`get_asset` resolves a target's own live metadata (status, tags)
when a collector needs to enrich a :class:`~app.models.monitoring_target
.MonitoringTarget` row with the asset's current state.

**Honest gap**: ``services/inventory-service``'s own real REST surface
has no reverse "find assets by label" endpoint and no dynamic-group
membership query beyond static group membership -- "Target Groups"
resolves against a group's own static membership only.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx
from shared_core.exceptions.dependency import DependencyError


class InventoryClient:
    """Reads live asset state from the Inventory Service."""

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


__all__ = ["InventoryClient"]
