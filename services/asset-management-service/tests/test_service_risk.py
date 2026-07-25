"""Tests for :class:`app.services.risk.RiskService`."""

from __future__ import annotations

from shared_core.events.base import DomainEvent
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import RiskLevel, RiskType
from app.repositories.asset_risk import AssetRiskRepository
from app.repositories.managed_asset import ManagedAssetRepository
from app.services.risk import EventPublisher, RiskService
from tests.conftest import make_managed_asset


def _build(db_session: AsyncSession, *, publish_event: EventPublisher | None = None) -> RiskService:
    return RiskService(
        AssetRiskRepository(db_session),
        ManagedAssetRepository(db_session),
        publish_event=publish_event,
    )


async def test_evaluate_sets_aggregate_score(db_session: AsyncSession) -> None:
    managed_asset = await make_managed_asset(db_session)
    service = _build(db_session)

    await service.evaluate(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        risk_type=RiskType.OPERATIONAL,
        level=RiskLevel.MEDIUM,
        score=40.0,
        mitigation_plan=None,
    )

    assert float(managed_asset.risk_score) == 40.0


async def test_evaluate_publishes_event_only_when_aggregate_changes(
    db_session: AsyncSession,
) -> None:
    published: list[DomainEvent] = []

    async def _publish(event: DomainEvent) -> None:
        published.append(event)

    managed_asset = await make_managed_asset(db_session)
    service = _build(db_session, publish_event=_publish)

    await service.evaluate(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        risk_type=RiskType.SECURITY,
        level=RiskLevel.HIGH,
        score=70.0,
        mitigation_plan="Patch the CVE",
    )
    assert len(published) == 1

    # Evaluating a lower-scored risk type doesn't lower the aggregate
    # (max across types), so no second event should fire.
    await service.evaluate(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        risk_type=RiskType.VENDOR,
        level=RiskLevel.LOW,
        score=10.0,
        mitigation_plan=None,
    )
    assert len(published) == 1
    assert float(managed_asset.risk_score) == 70.0


async def test_evaluate_publishes_again_when_aggregate_increases(db_session: AsyncSession) -> None:
    published: list[DomainEvent] = []

    async def _publish(event: DomainEvent) -> None:
        published.append(event)

    managed_asset = await make_managed_asset(db_session)
    service = _build(db_session, publish_event=_publish)

    await service.evaluate(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        risk_type=RiskType.BUSINESS,
        level=RiskLevel.LOW,
        score=20.0,
        mitigation_plan=None,
    )
    await service.evaluate(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        risk_type=RiskType.COMPLIANCE,
        level=RiskLevel.CRITICAL,
        score=95.0,
        mitigation_plan="Immediate remediation",
    )

    assert len(published) == 2
    assert float(managed_asset.risk_score) == 95.0


async def test_list_for_managed_asset_newest_first(db_session: AsyncSession) -> None:
    managed_asset = await make_managed_asset(db_session)
    service = _build(db_session)
    await service.evaluate(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        risk_type=RiskType.OPERATIONAL,
        level=RiskLevel.LOW,
        score=10.0,
        mitigation_plan=None,
    )
    await service.evaluate(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        risk_type=RiskType.OPERATIONAL,
        level=RiskLevel.MEDIUM,
        score=30.0,
        mitigation_plan=None,
    )

    records = await service.list_for_managed_asset(managed_asset.id)
    assert len(records) == 2
