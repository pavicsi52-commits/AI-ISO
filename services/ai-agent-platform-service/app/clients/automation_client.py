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

    @staticmethod
    def _envelope(response: httpx.Response, *, doing: str) -> dict[str, Any]:
        """Unwrap this platform's own ``SuccessResponse`` envelope.

        A sibling service that answers with the right status code but a
        body this service cannot read is a dependency failure like any
        other -- version skew, or a proxy substituting its own page --
        so it surfaces as :class:`DependencyError`, never as a raw
        ``KeyError``/``JSONDecodeError`` escaping this client's own
        documented contract.

        Raises:
            DependencyError: If the body isn't JSON, isn't an object, or
                carries no ``data`` object.
        """
        try:
            body = response.json()
        except ValueError as exc:
            raise DependencyError(
                f"Automation Service returned a non-JSON body {doing}: {exc}"
            ) from exc
        if not isinstance(body, dict) or not isinstance(body.get("data"), dict):
            raise DependencyError(
                f"Automation Service returned a body with no 'data' object {doing}."
            )
        return dict(body["data"])

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
        dispatched = self._envelope(response, doing=f"dispatching job {job_id!s}")
        execution_id = dispatched.get("id")
        if not execution_id:
            raise DependencyError(
                f"Automation Service dispatched job {job_id!s} without returning an execution id."
            )

        for _attempt in range(self._max_poll_attempts):
            execution = await self._get_execution(str(execution_id))
            status = execution.get("status")
            if status in _TERMINAL_STATUSES:
                if status != "completed":
                    raise DependencyError(
                        f"Automation job {job_id!r} execution {execution_id!r} ended in "
                        f"status {status!r}: {execution.get('error_message')}"
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
        return self._envelope(response, doing=f"reading execution {execution_id!r}")


__all__ = ["AutomationClient"]
