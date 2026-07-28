"""Suppression rule CRUD plus the suppression decision itself."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.models.alert_suppression import AlertSuppression
from app.models.enums import SuppressionType
from app.repositories.alert_maintenance_window import AlertMaintenanceWindowRepository
from app.repositories.alert_suppression import AlertSuppressionRepository
from app.suppression.engine import SuppressionDecision, evaluate_suppression


class AlertSuppressionService:
    """Creates and reads suppression rules, and decides suppression."""

    def __init__(
        self,
        suppressions: AlertSuppressionRepository,
        maintenance_windows: AlertMaintenanceWindowRepository,
    ) -> None:
        self._suppressions = suppressions
        self._maintenance_windows = maintenance_windows

    async def list_for_org(self, organization_id: UUID) -> list[AlertSuppression]:
        """Every suppression rule belonging to *organization_id*."""
        return await self._suppressions.list_for_org(organization_id)

    async def create(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        suppression_type: SuppressionType,
        scope_reference: str | None,
        reason: str | None,
        starts_at: datetime,
        ends_at: datetime | None,
        enabled: bool,
    ) -> AlertSuppression:
        """Create a suppression rule."""
        return await self._suppressions.create(
            AlertSuppression(
                organization_id=organization_id,
                project_id=project_id,
                suppression_type=suppression_type,
                scope_reference=scope_reference,
                reason=reason,
                starts_at=starts_at,
                ends_at=ends_at,
                enabled=enabled,
            )
        )

    async def decide(
        self,
        organization_id: UUID,
        source_reference: dict[str, Any],
        *,
        moment: datetime | None = None,
    ) -> SuppressionDecision:
        """Decide whether an alert with *source_reference* is suppressed."""
        now = moment or datetime.now(UTC)
        suppressions = await self._suppressions.list_active_at(organization_id, now)
        windows = await self._maintenance_windows.list_enabled_for_org(organization_id)
        return evaluate_suppression(
            source_reference=source_reference,
            suppressions=suppressions,
            maintenance_windows=windows,
            moment=now,
        )


__all__ = ["AlertSuppressionService"]
