"""Live lookups against the Validation Service, backing docs/044
"INTEGRATIONS": "Validation (Prompt 043)" -- folding a target's own
most recent validation posture into its ``COMPONENT_HEALTH`` signal (a
target that is currently failing its own validation checks is not
fully healthy even if every collected metric looks normal), reusing the
real ``GET /validation-results``/``GET /validation-results/executions/
{id}/score`` endpoints ``services/validation-service`` itself already
exposes.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx
from shared_core.exceptions.dependency import DependencyError


class ValidationClient:
    """Reads live validation results/scores from the Validation Service."""

    def __init__(self, client: httpx.AsyncClient, *, base_url: str, caller_token: str) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._caller_token = caller_token

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._caller_token}"}

    async def get_results_for_target(self, target_id: UUID) -> list[dict[str, Any]]:
        """Every validation result ever recorded against *target_id*.

        Raises:
            DependencyError: If the Validation Service is unreachable.
        """
        try:
            response = await self._client.get(
                f"{self._base_url}/validation-results",
                params={"target_id": str(target_id)},
                headers=self._headers(),
            )
        except httpx.HTTPError as exc:
            raise DependencyError(f"Validation Service unreachable: {exc}") from exc
        if response.status_code != httpx.codes.OK:
            raise DependencyError(
                f"Validation Service returned HTTP {response.status_code} "
                f"reading results for target {target_id!r}."
            )
        return list(response.json()["data"])

    async def get_execution_score(self, execution_id: UUID) -> dict[str, Any] | None:
        """Return *execution_id*'s own weighted score, or ``None`` if none
        has been computed yet.

        Raises:
            DependencyError: If the Validation Service is unreachable.
        """
        try:
            response = await self._client.get(
                f"{self._base_url}/validation-results/executions/{execution_id}/score",
                headers=self._headers(),
            )
        except httpx.HTTPError as exc:
            raise DependencyError(f"Validation Service unreachable: {exc}") from exc
        if response.status_code == httpx.codes.NOT_FOUND:
            return None
        if response.status_code != httpx.codes.OK:
            raise DependencyError(
                f"Validation Service returned HTTP {response.status_code} "
                f"reading score for execution {execution_id!r}."
            )
        return dict(response.json()["data"])


__all__ = ["ValidationClient"]
