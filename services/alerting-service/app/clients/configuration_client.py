"""Live lookups against the Configuration Management Service, backing
docs/045 "ALERT SOURCES": Configuration Management.

Reads that service's own real ``GET /configurations/drift`` endpoint
(verified against its own router) so unresolved configuration drift can
raise an alert.

**Honest gap**: those endpoints return *already-recorded* evaluations
-- there is no "run a live desired-state-vs-actual compare now"
trigger, the same gap ``services/validation-service`` and
``services/monitoring-service`` both already documented for the
identical service.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx
from shared_core.exceptions.dependency import DependencyError


class ConfigurationClient:
    """Reads already-recorded drift evaluations from Configuration Management."""

    def __init__(self, client: httpx.AsyncClient, *, base_url: str, caller_token: str) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._caller_token = caller_token

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._caller_token}"}

    async def get_drift(self, organization_id: UUID, profile_id: UUID) -> list[dict[str, Any]]:
        """Every already-recorded drift evaluation for *profile_id*.

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


__all__ = ["ConfigurationClient"]
