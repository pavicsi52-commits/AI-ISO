"""Live lookups against the Inventory Service, backing docs/042
"INVENTORY INTEGRATION" "Integrate Prompt 036": Dynamic Target
Resolution, Topology Queries, Group Resolution, Label Resolution, Asset
Context.

A ``TASK``/``CONNECTOR`` node's own ``config`` can name a target either
directly (a fixed ``target_ids`` list, resolved with no help from this
client) or dynamically via ``group_id`` -- :meth:`resolve_group_members`
resolves the latter into concrete asset ids ("Dynamic Target
Resolution"/"Group Resolution") before
:class:`~app.clients.automation_client.AutomationClient` dispatches
against them.

"Label Resolution" and "Topology Queries" are honestly NOT implemented
here: ``services/inventory-service``'s own real REST surface has no
reverse "find assets by label" endpoint (``GET /inventory/assets``
takes only ``organization_id``; ``GET /inventory/search`` filters by
``asset_type``/``status``/``owner_id``/``project_id``, never by label)
and this service's own node handlers have no genuine need for a
topology graph today -- the same "a required capability with no
reachable endpoint on the other side of the wire is an honest platform
gap, not something to fake" precedent
``app/clients/playbook_client.py``'s own "Dependency Resolution" gap
already established.
"""

from __future__ import annotations

from uuid import UUID

import httpx
from shared_core.exceptions.dependency import DependencyError


class InventoryClient:
    """Resolves dynamic group/label target references against the Inventory Service."""

    def __init__(self, client: httpx.AsyncClient, *, base_url: str, caller_token: str) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._caller_token = caller_token

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._caller_token}"}

    async def resolve_group_members(self, group_id: UUID) -> list[UUID]:
        """Every asset id belonging to *group_id* ("Group Resolution").

        Raises:
            DependencyError: If the Inventory Service is unreachable or
                *group_id* does not exist.
        """
        try:
            response = await self._client.get(
                f"{self._base_url}/inventory/groups/{group_id}/members", headers=self._headers()
            )
        except httpx.HTTPError as exc:
            raise DependencyError(f"Inventory Service unreachable: {exc}") from exc
        if response.status_code != httpx.codes.OK:
            raise DependencyError(
                f"Inventory Service returned HTTP {response.status_code} "
                f"resolving group {group_id!r}."
            )
        return [UUID(str(asset["id"])) for asset in response.json()["data"]]


__all__ = ["InventoryClient"]
