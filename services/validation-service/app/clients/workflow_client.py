"""Live lookups against the Workflow Runtime Service, backing docs/043
"WORKFLOW RUNTIME" "Integrate Prompt 042": Validation Nodes, Workflow
Gates, Conditional Branches -- reading whether a
``WORKFLOW_EXECUTION``-type target's own instance completed
successfully, and its own per-node step outcomes, before this
service's own rules decide pass/fail/warn.

"Approval Decisions" and "Validation Events" are satisfied without a
dedicated client method: an approval decision is just one more field
on the instance/step data this client already reads, and "Validation
Events" are this service's own outbound events
(:mod:`app.events.validation_events`), not something read from
workflow-runtime-service.
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
