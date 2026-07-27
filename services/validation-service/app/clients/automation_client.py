"""Live lookups against the Automation Service, backing docs/043
"AUTOMATION INTEGRATION" "Integrate Prompt 040": Pre Validation, Post
Validation, Execution Validation, Rollback Validation.

Two distinct uses: :meth:`get_latest_execution_for_job` reads an
``AUTOMATION_JOB``-type target's own most recent run status
(read-only, non-invasive -- the default for "Execution Validation");
:meth:`execute_and_wait` actively dispatches a live check job and
waits for it, for the rarer case a check genuinely needs to *run*
something rather than only read prior state ("Pre Validation"/"Post
Validation" gates around a real deployment step).

**Honest gap**: ``services/automation-service``'s own
``GET /automation/executions`` filters only by ``organization_id``/
``status`` -- there is no "list executions for job X" query parameter.
:meth:`get_latest_execution_for_job` fetches every execution in the
organization and filters by ``job_id`` client-side rather than
inventing a server-side filter the real endpoint doesn't support.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

import httpx
from shared_core.exceptions.dependency import DependencyError

_TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})


class AutomationClient:
    """Reads automation job execution history, and can dispatch a live check job."""

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

    async def get_latest_execution_for_job(
        self, organization_id: UUID, job_id: UUID
    ) -> dict[str, Any] | None:
        """Return *job_id*'s own most recent execution, or ``None`` if it
        has never run ("Execution Validation").

        Raises:
            DependencyError: If the Automation Service is unreachable.
        """
        try:
            response = await self._client.get(
                f"{self._base_url}/automation/executions",
                params={"organization_id": str(organization_id)},
                headers=self._headers(),
            )
        except httpx.HTTPError as exc:
            raise DependencyError(f"Automation Service unreachable: {exc}") from exc
        if response.status_code != httpx.codes.OK:
            raise DependencyError(
                f"Automation Service returned HTTP {response.status_code} listing executions."
            )
        for execution in response.json()["data"]:
            if execution.get("job_id") == str(job_id):
                return dict(execution)
        return None

    async def execute_and_wait(
        self, job_id: UUID, *, variables: dict[str, Any], target_ids: list[UUID] | None = None
    ) -> dict[str, Any]:
        """Dispatch *job_id* as a live check and wait for it to reach a
        terminal status ("Pre Validation"/"Post Validation").

        Raises:
            DependencyError: If the Automation Service is unreachable,
                the job doesn't exist, or the execution never reaches a
                terminal status within the configured polling attempts.
        """
        try:
            response = await self._client.post(
                f"{self._base_url}/automation/jobs/{job_id}/execute",
                json={
                    "target_ids": [str(target_id) for target_id in (target_ids or [])],
                    "variables": variables,
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
