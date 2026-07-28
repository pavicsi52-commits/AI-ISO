"""Live calls against the Workflow Runtime Service, backing docs/045
"ALERT SOURCES": Workflow Runtime, "CORRELATION" "Support": Workflow
Correlation, and "ESCALATION" "Support": Workflow Escalation.

Two distinct uses: :meth:`get_instance` reads a workflow instance's own
status (read-only, for correlation); :meth:`execute_workflow` actively
launches a remediation workflow, which is what an escalation level of
type ``WORKFLOW`` resolves to -- the one place this service genuinely
*acts* on another service rather than only reading from it.

Both endpoints were verified against ``services/workflow-runtime-service``'s
own routers rather than assumed: an earlier draft of this client
posted to a ``POST /workflow-instances`` endpoint that does not exist
(instances are created *by* executing a workflow, never registered
directly).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx
from shared_core.exceptions.dependency import DependencyError


class WorkflowRuntimeClient:
    """Reads workflow instance state, and can launch a remediation workflow."""

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

    async def execute_workflow(
        self, workflow_id: UUID, *, variables: dict[str, Any]
    ) -> dict[str, Any]:
        """Launch *workflow_id* as a new instance ("Workflow Escalation").

        Calls ``POST /workflows/{id}/execute`` -- the real endpoint that
        service exposes for starting a run (there is no
        ``POST /workflow-instances``; instances are created *by*
        executing a workflow, never registered directly).

        Raises:
            DependencyError: If the Workflow Runtime Service is
                unreachable or refuses the request.
        """
        try:
            response = await self._client.post(
                f"{self._base_url}/workflows/{workflow_id}/execute",
                json={"variables": variables},
                headers=self._headers(),
            )
        except httpx.HTTPError as exc:
            raise DependencyError(f"Workflow Runtime Service unreachable: {exc}") from exc
        if response.status_code != httpx.codes.CREATED:
            raise DependencyError(
                f"Workflow Runtime Service returned HTTP {response.status_code} "
                f"executing workflow {workflow_id!r}."
            )
        return dict(response.json()["data"])


__all__ = ["WorkflowRuntimeClient"]
