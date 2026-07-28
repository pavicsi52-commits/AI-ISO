"""Live lookups against the Automation Service, backing docs/045
"ALERT SOURCES": Automation.

Reads ``services/automation-service``'s own real
``GET /automation/executions`` endpoint (verified against that
service's own router) so a failed automation run can raise an alert
and a rule of type ``METRIC_THRESHOLD``/``CUSTOM_EXPRESSION`` can be
evaluated against real execution state.

**Honest gap**: that endpoint filters only by ``organization_id``/
``status`` -- there is no "list executions for job X" query parameter,
the same gap ``services/validation-service`` and
``services/monitoring-service`` both already documented for the
identical service. :meth:`get_latest_execution_for_job` filters
client-side rather than inventing a server-side filter that doesn't
exist.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx
from shared_core.exceptions.dependency import DependencyError


class AutomationClient:
    """Reads automation execution state from the Automation Service."""

    def __init__(self, client: httpx.AsyncClient, *, base_url: str, caller_token: str) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._caller_token = caller_token

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._caller_token}"}

    async def list_executions(
        self, organization_id: UUID, *, status: str | None = None
    ) -> list[dict[str, Any]]:
        """Every automation execution for *organization_id*.

        Raises:
            DependencyError: If the Automation Service is unreachable.
        """
        params: dict[str, str] = {"organization_id": str(organization_id)}
        if status is not None:
            params["status"] = status
        try:
            response = await self._client.get(
                f"{self._base_url}/automation/executions",
                params=params,
                headers=self._headers(),
            )
        except httpx.HTTPError as exc:
            raise DependencyError(f"Automation Service unreachable: {exc}") from exc
        if response.status_code != httpx.codes.OK:
            raise DependencyError(
                f"Automation Service returned HTTP {response.status_code} listing executions."
            )
        return list(response.json()["data"])

    async def get_latest_execution_for_job(
        self, organization_id: UUID, job_id: UUID
    ) -> dict[str, Any] | None:
        """Return *job_id*'s own most recent execution, or ``None``."""
        for execution in await self.list_executions(organization_id):
            if execution.get("job_id") == str(job_id):
                return dict(execution)
        return None


__all__ = ["AutomationClient"]
