"""Live lookups against the Workflow Runtime Service, backing docs/044
"INTEGRATIONS": "Workflow Runtime (Prompt 042)" -- folding an
orchestrated pipeline's own most recent instance outcome into
``DEPENDENCY_HEALTH``/``APPLICATION_HEALTH`` for any target whose own
operational health depends on that pipeline completing successfully
(e.g. a nightly backup or deployment workflow a database target's own
health implicitly depends on).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx
from shared_core.exceptions.dependency import DependencyError


class WorkflowRuntimeClient:
    """Reads live workflow instance/step state from the Workflow Runtime Service."""

    def __init__(self, client: httpx.AsyncClient, *, base_url: str, caller_token: str) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._caller_token = caller_token

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._caller_token}"}

    async def get_instance(self, instance_id: UUID) -> dict[str, Any]:
        """Return *instance_id*'s own live record.

        Raises:
            DependencyError: If the Workflow Runtime Service is
                unreachable or *instance_id* does not exist.
        """
        try:
            response = await self._client.get(
                f"{self._base_url}/workflow-instances/{instance_id}", headers=self._headers()
            )
        except httpx.HTTPError as exc:
            raise DependencyError(f"Workflow Runtime Service unreachable: {exc}") from exc
        if response.status_code != httpx.codes.OK:
            raise DependencyError(
                f"Workflow Runtime Service returned HTTP {response.status_code} "
                f"reading instance {instance_id!r}."
            )
        return dict(response.json()["data"])

    async def list_steps(self, instance_id: UUID) -> list[dict[str, Any]]:
        """Every per-node execution result for *instance_id*.

        Raises:
            DependencyError: If the Workflow Runtime Service is unreachable.
        """
        try:
            response = await self._client.get(
                f"{self._base_url}/workflow-instances/{instance_id}/steps",
                headers=self._headers(),
            )
        except httpx.HTTPError as exc:
            raise DependencyError(f"Workflow Runtime Service unreachable: {exc}") from exc
        if response.status_code != httpx.codes.OK:
            raise DependencyError(
                f"Workflow Runtime Service returned HTTP {response.status_code} "
                f"reading steps for instance {instance_id!r}."
            )
        return list(response.json()["data"])


__all__ = ["WorkflowRuntimeClient"]
