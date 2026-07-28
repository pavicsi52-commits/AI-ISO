"""Read-only clients for the platform services this assistant answers
questions about ("KNOWLEDGE SOURCES", "TOOL CALLING").

One class rather than eight near-identical files: every one of these
calls is the same shape -- authenticated ``GET``, unwrap
``{"data": ...}``, raise :class:`AIError` on failure -- and the only
thing that varies is the base URL and path. Eight classes would be
copy-paste with different constants.

Every endpoint used here was verified against the owning service's own
router, not assumed from its prompt document. Where a needed query
does not exist, that gap is documented rather than papered over with a
guessed path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
from shared_core.exceptions.ai import AIError


@dataclass(frozen=True, slots=True)
class PlatformEndpoints:
    """Base URLs of every platform service this assistant reads."""

    inventory: str
    discovery: str
    configuration: str
    automation: str
    workflow: str
    validation: str
    monitoring: str
    alerting: str


class PlatformClient:
    """Authenticated read access to the rest of the platform.

    Every call carries the *caller's own* bearer token, never a service
    credential. That is deliberate: it means the assistant can never
    read anything the asking user could not read themselves, so RBAC is
    enforced by the owning service rather than reimplemented here.
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        endpoints: PlatformEndpoints,
        *,
        caller_token: str,
    ) -> None:
        self._client = client
        self._endpoints = endpoints
        self._caller_token = caller_token

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._caller_token}"}

    async def _get(
        self, service: str, base_url: str, path: str, params: dict[str, Any] | None = None
    ) -> Any:
        """Issue one authenticated GET and unwrap its envelope.

        Raises:
            AIError: If the service is unreachable or returns non-200.
                Raised as ``AIError`` (not ``DependencyError``) because
                the caller is always an AI turn, and this is the error
                the chat layer knows how to surface to a user.
        """
        try:
            response = await self._client.get(
                f"{base_url.rstrip('/')}{path}", params=params, headers=self._headers()
            )
        except httpx.HTTPError as exc:
            raise AIError(f"{service} is unreachable: {exc}") from exc
        if response.status_code != httpx.codes.OK:
            raise AIError(f"{service} returned HTTP {response.status_code} for {path!r}.")
        return response.json().get("data")

    async def list_assets(self, organization_id: str) -> list[dict[str, Any]]:
        """Inventory assets for an organization."""
        data = await self._get(
            "inventory-service",
            self._endpoints.inventory,
            "/inventory/assets",
            {"organization_id": organization_id},
        )
        return list(data or [])

    async def get_asset(self, asset_id: str) -> dict[str, Any]:
        """One inventory asset."""
        return dict(
            await self._get(
                "inventory-service", self._endpoints.inventory, f"/inventory/assets/{asset_id}"
            )
            or {}
        )

    async def get_topology(self, asset_id: str, *, depth: int = 1) -> dict[str, Any]:
        """An asset's own topology neighbourhood ("Topology Questions")."""
        return dict(
            await self._get(
                "inventory-service",
                self._endpoints.inventory,
                "/inventory/topology",
                {"asset_id": asset_id, "query_kind": "neighbors", "depth": depth},
            )
            or {}
        )

    async def list_alerts(
        self, organization_id: str, *, status: str | None = None
    ) -> list[dict[str, Any]]:
        """Alerts for an organization ("Alert Queries", "Alert Explanation")."""
        params: dict[str, Any] = {"organization_id": organization_id}
        if status:
            params["status"] = status
        data = await self._get("alerting-service", self._endpoints.alerting, "/alerts", params)
        return list(data or [])

    async def get_monitoring_health(self, target_id: str) -> list[dict[str, Any]]:
        """A monitored target's own health results ("Health Summary")."""
        data = await self._get(
            "monitoring-service",
            self._endpoints.monitoring,
            "/monitoring/health",
            {"target_id": target_id},
        )
        return list(data or [])

    async def get_monitoring_statistics(self, organization_id: str) -> dict[str, Any]:
        """Monitoring analytics ("Metric Analysis", "Capacity Planning")."""
        return dict(
            await self._get(
                "monitoring-service",
                self._endpoints.monitoring,
                "/monitoring/statistics",
                {"organization_id": organization_id},
            )
            or {}
        )

    async def list_validation_results(self, target_id: str) -> list[dict[str, Any]]:
        """Validation results for a target ("Validation Summary")."""
        data = await self._get(
            "validation-service",
            self._endpoints.validation,
            "/validation-results",
            {"target_id": target_id},
        )
        return list(data or [])

    async def get_configuration_drift(
        self, organization_id: str, profile_id: str
    ) -> list[dict[str, Any]]:
        """Recorded configuration drift ("Drift Explanation")."""
        data = await self._get(
            "configuration-management-service",
            self._endpoints.configuration,
            "/configurations/drift",
            {"organization_id": organization_id, "profile_id": profile_id},
        )
        return list(data or [])

    async def list_automation_executions(self, organization_id: str) -> list[dict[str, Any]]:
        """Automation execution history ("Automation Reports")."""
        data = await self._get(
            "automation-service",
            self._endpoints.automation,
            "/automation/executions",
            {"organization_id": organization_id},
        )
        return list(data or [])

    async def get_workflow_instance(self, instance_id: str) -> dict[str, Any]:
        """One workflow instance's own state."""
        return dict(
            await self._get(
                "workflow-runtime-service",
                self._endpoints.workflow,
                f"/workflow-instances/{instance_id}",
            )
            or {}
        )

    async def get_discovery_job(self, job_id: str) -> dict[str, Any]:
        """One discovery job's own summary."""
        return dict(
            await self._get(
                "discovery-service", self._endpoints.discovery, f"/discovery/jobs/{job_id}"
            )
            or {}
        )


__all__ = ["PlatformClient", "PlatformEndpoints"]
