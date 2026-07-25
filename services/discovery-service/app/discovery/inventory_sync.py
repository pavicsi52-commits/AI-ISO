"""Live synchronization of discovered assets/relationships into the
Inventory Service.

Per docs/037 "INVENTORY SYNCHRONIZATION": "Integrate with Prompt 036."
Create Assets, Update Assets, Merge Assets, Conflict Detection,
Duplicate Detection, Asset Reconciliation, Relationship Synchronization,
Topology Updates. This client talks to
``services/inventory-service``'s own REST API rather than its
database directly (services never share a database in this platform)
-- Neo4j topology updates happen automatically as a side effect of
that service's own ``AssetRelationshipService``, so this client never
touches Neo4j itself.

**Conflict resolution**: ``POST /inventory/assets`` enforces "Prevent
duplicate identifiers" (hostname/serial/MAC unique per organization,
per ``services/inventory-service``'s own ``AssetService.create()``).
A ``409`` there is *expected*, not a failure -- it means an asset with
this identifier already exists, so :meth:`InventorySyncClient.sync_asset`
falls back to ``GET /inventory/search`` to find it and
``PUT /inventory/assets/{id}`` to reconcile its fields instead. This is
the "Conflict Detection"/"Asset Reconciliation" docs/037 asks for,
built entirely on the Inventory Service's own existing REST surface
rather than requiring a new endpoint there.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx
from shared_core.exceptions.dependency import DependencyError

from app.models.discovery_asset import DiscoveryAsset
from app.models.discovery_relationship import DiscoveryRelationship
from app.models.enums import DiscoveryRelationshipType


class InventorySyncClient:
    """Creates or updates assets, and creates relationships, in the
    Inventory Service.
    """

    def __init__(self, client: httpx.AsyncClient, *, base_url: str) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")

    async def sync_asset(
        self,
        asset: DiscoveryAsset,
        *,
        organization_id: UUID,
        caller_token: str,
        identifiers: dict[str, str | None],
    ) -> tuple[UUID, bool]:
        """Create (or, on a duplicate-identifier conflict, update) the
        Inventory Service asset corresponding to *asset*.

        Returns:
            The Inventory Service's own ``Asset.id``, and whether a new
            asset was created there (``False`` means an existing one was
            reconciled instead -- see :meth:`_reconcile_existing`).

        Raises:
            DependencyError: If the Inventory Service is unreachable or
                denies access.
        """
        headers = {"Authorization": f"Bearer {caller_token}"}
        body: dict[str, Any] = {
            "organization_id": str(organization_id),
            "name": asset.name,
            "hostname": identifiers.get("hostname"),
            "serial_number": identifiers.get("serial_number"),
            "mac_address": identifiers.get("mac_address"),
            "ip_address": identifiers.get("ip_address"),
            "asset_type": asset.asset_type,
            "vendor": asset.fingerprint.get("vendor"),
            "manufacturer": asset.fingerprint.get("manufacturer"),
            "model": asset.fingerprint.get("model"),
            "firmware_version": asset.fingerprint.get("firmware_version"),
            "operating_system": asset.fingerprint.get("operating_system"),
            "architecture": asset.fingerprint.get("architecture"),
            "metadata": asset.fingerprint,
        }
        try:
            response = await self._client.post(
                f"{self._base_url}/inventory/assets", json=body, headers=headers
            )
        except httpx.HTTPError as exc:
            raise DependencyError(f"Inventory Service unreachable: {exc}") from exc

        if response.status_code == httpx.codes.CREATED:
            return UUID(response.json()["data"]["id"]), True
        if response.status_code == httpx.codes.CONFLICT:
            reconciled_id = await self._reconcile_existing(
                body, organization_id=organization_id, headers=headers
            )
            return reconciled_id, False
        if response.status_code in (401, 403):
            raise DependencyError("Not authorized to create assets in the Inventory Service.")
        raise DependencyError(
            f"Inventory Service returned HTTP {response.status_code} creating an asset."
        )

    async def _reconcile_existing(
        self, body: dict[str, Any], *, organization_id: UUID, headers: dict[str, str]
    ) -> UUID:
        """Find the pre-existing asset a duplicate-identifier conflict
        named, and reconcile its fields via ``PUT``.
        """
        query = body.get("hostname") or body.get("serial_number") or body.get("mac_address")
        try:
            response = await self._client.get(
                f"{self._base_url}/inventory/search",
                params={"organization_id": str(organization_id), "q": query},
                headers=headers,
            )
        except httpx.HTTPError as exc:
            raise DependencyError(f"Inventory Service unreachable: {exc}") from exc
        if response.status_code != httpx.codes.OK:
            raise DependencyError(
                f"Inventory Service returned HTTP {response.status_code} searching for a conflict."
            )
        items = response.json()["data"]["items"]
        if not items:
            raise DependencyError("Duplicate-identifier conflict reported, but no match found.")
        existing_id = items[0]["id"]

        update_body = {
            "name": body["name"],
            "hostname": body.get("hostname"),
            "serial_number": body.get("serial_number"),
            "mac_address": body.get("mac_address"),
            "ip_address": body.get("ip_address"),
            "vendor": body.get("vendor"),
            "manufacturer": body.get("manufacturer"),
            "model": body.get("model"),
            "firmware_version": body.get("firmware_version"),
            "operating_system": body.get("operating_system"),
            "architecture": body.get("architecture"),
            "status": items[0]["status"],
            "health": items[0]["health"],
            "lifecycle_state": items[0]["lifecycle_state"],
            "criticality": items[0]["criticality"],
            "metadata": body.get("metadata", {}),
        }
        update_response = await self._client.put(
            f"{self._base_url}/inventory/assets/{existing_id}", json=update_body, headers=headers
        )
        if update_response.status_code != httpx.codes.OK:
            raise DependencyError(
                f"Inventory Service returned HTTP {update_response.status_code} reconciling asset."
            )
        return UUID(existing_id)

    async def sync_relationship(
        self,
        relationship: DiscoveryRelationship,
        *,
        organization_id: UUID,
        source_inventory_asset_id: UUID,
        target_inventory_asset_id: UUID,
        caller_token: str,
    ) -> None:
        """Create the Inventory Service relationship corresponding to
        *relationship*, tolerating an already-existing edge.
        """
        headers = {"Authorization": f"Bearer {caller_token}"}
        body = {
            "organization_id": str(organization_id),
            "source_asset_id": str(source_inventory_asset_id),
            "target_asset_id": str(target_inventory_asset_id),
            "relationship_type": _to_inventory_relationship_type(relationship.relationship_type),
        }
        try:
            response = await self._client.post(
                f"{self._base_url}/inventory/relationships", json=body, headers=headers
            )
        except httpx.HTTPError as exc:
            raise DependencyError(f"Inventory Service unreachable: {exc}") from exc
        if response.status_code in (httpx.codes.CREATED, httpx.codes.CONFLICT):
            return
        if response.status_code in (401, 403):
            raise DependencyError(
                "Not authorized to create relationships in the Inventory Service."
            )
        raise DependencyError(
            f"Inventory Service returned HTTP {response.status_code} creating a relationship."
        )


_RELATIONSHIP_TYPE_MAP: dict[DiscoveryRelationshipType, str] = {
    DiscoveryRelationshipType.RUNS_ON: "runs_on",
    DiscoveryRelationshipType.CONNECTED_TO: "connected_to",
    DiscoveryRelationshipType.DEPENDS_ON: "depends_on",
    DiscoveryRelationshipType.HOSTED_BY: "hosted_by",
    DiscoveryRelationshipType.CONTAINS: "contains",
    DiscoveryRelationshipType.COMMUNICATES_WITH: "communicates_with",
    DiscoveryRelationshipType.MANAGED_BY: "managed_by",
    DiscoveryRelationshipType.MEMBER_OF: "member_of",
    DiscoveryRelationshipType.PART_OF: "part_of",
}
"""Every :class:`DiscoveryRelationshipType` maps onto one of
``services/inventory-service``'s own (larger, 16-value)
``RelationshipType`` -- the nine discovery-side values are a strict
subset by name, so this is a direct, total mapping, not a lossy one.
"""


def _to_inventory_relationship_type(relationship_type: DiscoveryRelationshipType) -> str:
    return _RELATIONSHIP_TYPE_MAP[relationship_type]


__all__ = ["InventorySyncClient"]
