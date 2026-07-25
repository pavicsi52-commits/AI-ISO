"""Risk assessment. Per docs/038 "RISK MANAGEMENT" "Evaluate":
Operational, Security, Business, Vendor, Compliance Risk, Risk Scoring,
Mitigation Plans, Risk History.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID

from shared_core.events.base import DomainEvent

from app.events.asset_events import RiskScoreChangedEvent
from app.models.asset_risk import AssetRisk
from app.models.enums import RiskLevel, RiskType
from app.repositories.asset_risk import AssetRiskRepository
from app.repositories.managed_asset import ManagedAssetRepository

EventPublisher = Callable[[DomainEvent], Awaitable[None]]


class RiskService:
    """Evaluates and lists risk assessments for a managed asset."""

    def __init__(
        self,
        risks: AssetRiskRepository,
        managed_assets: ManagedAssetRepository,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._risks = risks
        self._managed_assets = managed_assets
        self._publish_event = publish_event

    async def _publish(self, event: DomainEvent) -> None:
        if self._publish_event is not None:
            await self._publish_event(event)

    async def list_for_managed_asset(self, managed_asset_id: UUID) -> list[AssetRisk]:
        """Every risk-type evaluation for *managed_asset_id* ("Risk History")."""
        return await self._risks.list_for_managed_asset(managed_asset_id)

    async def evaluate(
        self,
        managed_asset_id: UUID,
        *,
        organization_id: UUID,
        risk_type: RiskType,
        level: RiskLevel,
        score: float,
        mitigation_plan: str | None,
    ) -> AssetRisk:
        """Record a risk-type evaluation ("Evaluate"/"Risk Scoring"),
        rolling the managed asset's aggregate risk score up to the
        highest currently-known score and publishing
        ``RiskScoreChanged`` when that aggregate actually moves.
        """
        evaluation = await self._risks.create(
            AssetRisk(
                managed_asset_id=managed_asset_id,
                organization_id=organization_id,
                risk_type=risk_type,
                level=level,
                score=score,
                mitigation_plan=mitigation_plan,
                evaluated_at=datetime.now(UTC),
            )
        )

        all_current = await self.list_for_managed_asset(managed_asset_id)
        latest_per_type: dict[RiskType, float] = {}
        for entry in all_current:
            latest_per_type.setdefault(entry.risk_type, float(entry.score))
        aggregate_score = max(latest_per_type.values()) if latest_per_type else 0.0

        managed_asset = await self._managed_assets.require_by_id(managed_asset_id)
        previous_score = float(managed_asset.risk_score)
        if previous_score != aggregate_score:
            managed_asset.risk_score = aggregate_score
            await self._publish(
                RiskScoreChangedEvent(
                    source_service="asset-management-service",
                    payload={
                        "managed_asset_id": str(managed_asset_id),
                        "from": previous_score,
                        "to": aggregate_score,
                    },
                )
            )
        return evaluation


__all__ = ["RiskService"]
