"""Live dispatch against the Automation Service, backing this
service's ``AUTOMATION`` tool kind (docs/060 "TOOL EXECUTION").

Mirrors ``workflow-runtime-service``'s own ``app/clients
/automation_client.py`` (Prompt 042) shape closely -- rewritten here,
not imported, per this platform's zero-cross-service-import
convention: "services never share code, only ``shared_core``."

``caller_token`` is constructed fresh per tool call from whoever
initiated the owning :class:`~app.models.execution.AgentExecution`,
never a fixed service-wide credential -- an agent's own automation tool
call must act with the authority of the caller who triggered that
execution, matching the same precedent
``workflow-runtime-service``'s own ``ExecutionService._build_handler
_registry`` already established.
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
        reaches a terminal status.

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
