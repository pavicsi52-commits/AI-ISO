"""Compliance evaluation. Per docs/038 "COMPLIANCE" "Support": Security,
Configuration, License, Patch, Industry, Internal Policies Compliance,
Compliance Reports, Exceptions.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.events.base import DomainEvent

from app.events.asset_events import ComplianceFailedEvent
from app.models.asset_compliance import AssetCompliance
from app.models.enums import ComplianceStatus, ComplianceType
from app.repositories.asset_compliance import AssetComplianceRepository
from app.repositories.managed_asset import ManagedAssetRepository

EventPublisher = Callable[[DomainEvent], Awaitable[None]]

_WORST_FIRST = (
    ComplianceStatus.NON_COMPLIANT,
    ComplianceStatus.PARTIALLY_COMPLIANT,
    ComplianceStatus.EXCEPTION,
    ComplianceStatus.UNKNOWN,
    ComplianceStatus.COMPLIANT,
)


def _worst(statuses: list[ComplianceStatus]) -> ComplianceStatus:
    for candidate in _WORST_FIRST:
        if candidate in statuses:
            return candidate
    return ComplianceStatus.UNKNOWN


class ComplianceService:
    """Evaluates and lists compliance status for a managed asset."""

    def __init__(
        self,
        compliance: AssetComplianceRepository,
        managed_assets: ManagedAssetRepository,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._compliance = compliance
        self._managed_assets = managed_assets
        self._publish_event = publish_event

    async def _publish(self, event: DomainEvent) -> None:
        if self._publish_event is not None:
            await self._publish_event(event)

    async def list_for_managed_asset(
        self, managed_asset_id: UUID, *, compliance_type: ComplianceType | None = None
    ) -> list[AssetCompliance]:
        """Every compliance evaluation for *managed_asset_id* ("Compliance Reports")."""
        return await self._compliance.list_for_managed_asset(
            managed_asset_id, compliance_type=compliance_type
        )

    async def evaluate(
        self,
        managed_asset_id: UUID,
        *,
        organization_id: UUID,
        compliance_type: ComplianceType,
        status: ComplianceStatus,
        details: dict[str, Any],
        exception_reason: str | None,
    ) -> AssetCompliance:
        """Record a compliance-type evaluation ("Support"), rolling the
        managed asset's aggregate compliance status up to the worst
        currently-known status and publishing ``ComplianceFailed`` when
        *status* is ``NON_COMPLIANT``.
        """
        evaluation = await self._compliance.create(
            AssetCompliance(
                managed_asset_id=managed_asset_id,
                organization_id=organization_id,
                compliance_type=compliance_type,
                status=status,
                checked_at=datetime.now(UTC),
                details=details,
                exception_reason=exception_reason,
            )
        )

        all_current = await self.list_for_managed_asset(managed_asset_id)
        latest_per_type: dict[ComplianceType, ComplianceStatus] = {}
        for entry in all_current:
            latest_per_type.setdefault(entry.compliance_type, entry.status)
        managed_asset = await self._managed_assets.require_by_id(managed_asset_id)
        managed_asset.compliance_status = _worst(list(latest_per_type.values()))

        if status == ComplianceStatus.NON_COMPLIANT:
            await self._publish(
                ComplianceFailedEvent(
                    source_service="asset-management-service",
                    payload={
                        "managed_asset_id": str(managed_asset_id),
                        "compliance_type": str(compliance_type),
                    },
                )
            )
        return evaluation


__all__ = ["ComplianceService"]
