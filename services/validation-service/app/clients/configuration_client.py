"""Live lookups against the Configuration Management Service, backing
docs/043 "CONFIGURATION MANAGEMENT" "Integrate Prompt 039": validating
Configuration Drift and Policy Compliance (real endpoints -- see
below); Desired State/Baselines/Templates comparison is an honest
platform gap, not implemented here.

**Honest gap**: ``services/configuration-management-service`` exposes
``GET /configurations/drift``/``GET /configurations/compliance`` as
read-only lists of *already-recorded* evaluations -- there is no "run a
live desired-state-vs-actual compare right now" endpoint. This
service's own ``CONFIGURATION``/``COMPLIANCE`` collectors therefore
read whatever drift/compliance rows already exist for a profile rather
than triggering a fresh comparison, the same "an honest platform gap,
not something to fake" precedent
``app/clients/inventory_client.py``'s own docstring already documents
for a different service.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx
from shared_core.exceptions.dependency import DependencyError


class ConfigurationClient:
    """Reads already-recorded drift/compliance evaluations from the
    Configuration Management Service.
    """

    def __init__(self, client: httpx.AsyncClient, *, base_url: str, caller_token: str) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._caller_token = caller_token

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._caller_token}"}

    async def get_drift(self, organization_id: UUID, profile_id: UUID) -> list[dict[str, Any]]:
        """Every already-recorded drift evaluation for *profile_id* ("Configuration Drift").

        Raises:
            DependencyError: If the Configuration Management Service is unreachable.
        """
        try:
            response = await self._client.get(
                f"{self._base_url}/configurations/drift",
                params={"organization_id": str(organization_id), "profile_id": str(profile_id)},
                headers=self._headers(),
            )
        except httpx.HTTPError as exc:
            raise DependencyError(f"Configuration Management Service unreachable: {exc}") from exc
        if response.status_code != httpx.codes.OK:
            raise DependencyError(
                f"Configuration Management Service returned HTTP {response.status_code} "
                f"reading drift for profile {profile_id!r}."
            )
        return list(response.json()["data"])

    async def get_compliance(self, profile_id: UUID) -> list[dict[str, Any]]:
        """Every already-recorded compliance evaluation for *profile_id* ("Policy Compliance").

        Raises:
            DependencyError: If the Configuration Management Service is unreachable.
        """
        try:
            response = await self._client.get(
                f"{self._base_url}/configurations/compliance",
                params={"profile_id": str(profile_id)},
                headers=self._headers(),
            )
        except httpx.HTTPError as exc:
            raise DependencyError(f"Configuration Management Service unreachable: {exc}") from exc
        if response.status_code != httpx.codes.OK:
            raise DependencyError(
                f"Configuration Management Service returned HTTP {response.status_code} "
                f"reading compliance for profile {profile_id!r}."
            )
        return list(response.json()["data"])


__all__ = ["ConfigurationClient"]
