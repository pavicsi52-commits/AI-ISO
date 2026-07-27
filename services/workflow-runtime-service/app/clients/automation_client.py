"""Live dispatch against the Automation Service, backing this
service's ``TASK``/``CONNECTOR`` node handler.

Per docs/042 "AUTOMATION INTEGRATION" "Integrate Prompt 040": Automation
Tasks, Execution Callbacks, Automation Results, Rollback Coordination.
Also backs "CONNECTOR INTEGRATION" ("Integrate Prompt 027"): rather than
this service re-implementing SSH/WinRM/Redfish/SNMP/REST/Cloud/
Kubernetes/Industrial/Plugin dispatch a second time,
``services/automation-service``'s own
:class:`~app.models.automation_target.AutomationTarget
.connector_type` already selects the concrete provider per target --
a ``CONNECTOR``-type workflow node's ``job_id`` simply points at an
automation job pre-configured with the right target, so this one
client covers both node types identically.

There is no shared "execute_job_and_wait" function importable across
service boundaries -- services never share code, only ``shared_core`` --
so this client's own :meth:`AutomationClient.execute_and_wait` is what
``app/handlers/task.py`` passes into
:func:`shared_core.workflow.build_automation_task_handler`.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

import httpx
from shared_core.exceptions.dependency import DependencyError

_TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})


class AutomationClient:
    """Dispatches an automation job and waits for it to reach a terminal status."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        base_url: str,
        caller_token: str,
        poll_interval_seconds: float = 2.0,
        max_poll_attempts: int = 900,
    ) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._caller_token = caller_token
        self._poll_interval_seconds = poll_interval_seconds
        self._max_poll_attempts = max_poll_attempts

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._caller_token}"}

    async def execute_and_wait(
        self,
        job_id: UUID,
        *,
        variables: dict[str, Any],
        target_ids: list[UUID] | None = None,
        timeout_seconds: int | None = None,
    ) -> dict[str, Any]:
        """Execute *job_id* on the Automation Service and poll until it
        reaches a terminal status ("Execution Callbacks"/"Automation Results").

        Raises:
            DependencyError: If the Automation Service is unreachable,
                the job doesn't exist, or the execution never reaches a
                terminal status within ``max_poll_attempts``.
        """
        try:
            response = await self._client.post(
                f"{self._base_url}/automation/jobs/{job_id}/execute",
                json={
                    "target_ids": [str(target_id) for target_id in (target_ids or [])],
                    "variables": variables,
                    "timeout_seconds": timeout_seconds,
                },
                headers=self._headers(),
            )
        except httpx.HTTPError as exc:
            raise DependencyError(f"Automation Service unreachable: {exc}") from exc
        if response.status_code != httpx.codes.CREATED:
            raise DependencyError(
                f"Automation Service returned HTTP {response.status_code} "
                f"dispatching job {job_id!r}."
            )
        execution_id = response.json()["data"]["id"]

        for _attempt in range(self._max_poll_attempts):
            execution = await self._get_execution(execution_id)
            if execution["status"] in _TERMINAL_STATUSES:
                if execution["status"] != "completed":
                    raise DependencyError(
                        f"Automation job {job_id!r} execution {execution_id!r} ended in "
                        f"status {execution['status']!r}: {execution.get('error_message')}"
                    )
                return execution
            await asyncio.sleep(self._poll_interval_seconds)

        raise DependencyError(
            f"Automation job {job_id!r} execution {execution_id!r} did not reach a terminal "
            f"status within {self._max_poll_attempts} polling attempts."
        )

    async def _get_execution(self, execution_id: str) -> dict[str, Any]:
        try:
            response = await self._client.get(
                f"{self._base_url}/automation/executions/{execution_id}", headers=self._headers()
            )
        except httpx.HTTPError as exc:
            raise DependencyError(f"Automation Service unreachable: {exc}") from exc
        if response.status_code != httpx.codes.OK:
            raise DependencyError(
                f"Automation Service returned HTTP {response.status_code} "
                f"reading execution {execution_id!r}."
            )
        return dict(response.json()["data"])


__all__ = ["AutomationClient"]
