"""Alert route CRUD plus route selection ("ROUTING")."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from shared_core.enums.severity import Severity

from app.models.alert_route import AlertRoute
from app.models.enums import AlertRouteChannel, RouteTargetType
from app.repositories.alert_route import AlertRouteRepository
from app.routing.engine import select_routes


class AlertRouteService:
    """Creates and reads routes, and selects which fire for an alert."""

    def __init__(self, routes: AlertRouteRepository) -> None:
        self._routes = routes

    async def list_for_org(self, organization_id: UUID) -> list[AlertRoute]:
        """Every route belonging to *organization_id*."""
        return await self._routes.list_for_org(organization_id)

    async def create(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        name: str,
        channel: AlertRouteChannel,
        target_type: RouteTargetType,
        target_reference: str,
        configuration: dict[str, Any],
        severity_filter: Severity | None,
        enabled: bool,
    ) -> AlertRoute:
        """Create a routing configuration."""
        return await self._routes.create(
            AlertRoute(
                organization_id=organization_id,
                project_id=project_id,
                name=name,
                channel=channel,
                target_type=target_type,
                target_reference=target_reference,
                configuration=configuration,
                severity_filter=severity_filter,
                enabled=enabled,
            )
        )

    async def select_for_severity(
        self, organization_id: UUID, severity: Severity | str
    ) -> list[AlertRoute]:
        """Every route that should deliver an alert of *severity*."""
        enabled = await self._routes.list_enabled_for_org(organization_id)
        return select_routes(enabled, severity)


__all__ = ["AlertRouteService"]
