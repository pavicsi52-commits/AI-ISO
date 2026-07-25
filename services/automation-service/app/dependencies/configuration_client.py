"""Read-only lookups against
``services/configuration-management-service``'s own REST API.

Per docs/040 "CONFIGURATION MANAGEMENT" "Support": Desired State
Enforcement, Configuration Deployment, Drift Remediation, Baseline
Deployment, Configuration Validation. A configuration-enforcement job's
own execution content is generated from a profile's *current* desired
state (its latest version's ``content``), fetched live from that
service's own REST API rather than duplicating its own database, the
same "lean REST client, not a generated SDK" precedent
``app.inventory.inventory_client.InventoryClient`` established for the
equivalent Inventory Service integration.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx
from shared_core.exceptions.dependency import DependencyError


class ConfigurationClient:
    """Resolves configuration-management-service profiles for the current caller."""

    def __init__(self, client: httpx.AsyncClient, *, base_url: str) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")

    async def get_profile(self, profile_id: UUID, *, caller_token: str) -> dict[str, Any] | None:
        """Return the configuration profile identified by *profile_id*,
        or ``None`` if it doesn't exist.

        Raises:
            DependencyError: If the Configuration Management Service is
                unreachable or denies access for a reason other than
                "not found".
        """
        return await self._get(f"/configurations/{profile_id}", caller_token=caller_token)

    async def get_latest_version(
        self, profile_id: UUID, *, caller_token: str
    ) -> dict[str, Any] | None:
        """Return *profile_id*'s most recently recorded version ("Desired
        State Enforcement"), or ``None`` if it has no versions yet.

        Raises:
            DependencyError: If the Configuration Management Service is
                unreachable or denies access.
        """
        payload = await self._get(
            f"/configurations/{profile_id}/versions", caller_token=caller_token
        )
        if payload is None:
            return None
        versions = payload.get("items", payload) if isinstance(payload, dict) else payload
        if not isinstance(versions, list) or not versions:
            return None
        latest: dict[str, Any] = versions[0]
        return latest

    async def _get(self, path: str, *, caller_token: str) -> dict[str, Any] | None:
        headers = {"Authorization": f"Bearer {caller_token}"}
        try:
            response = await self._client.get(f"{self._base_url}{path}", headers=headers)
        except httpx.HTTPError as exc:
            raise DependencyError(f"Configuration Management Service unreachable: {exc}") from exc
        if response.status_code == httpx.codes.OK:
            data: dict[str, Any] = response.json()["data"]
            return data
        if response.status_code == httpx.codes.NOT_FOUND:
            return None
        if response.status_code in (401, 403):
            raise DependencyError(
                "Not authorized to read this resource in the Configuration Management Service."
            )
        raise DependencyError(
            f"Configuration Management Service returned HTTP {response.status_code}."
        )


__all__ = ["ConfigurationClient"]
