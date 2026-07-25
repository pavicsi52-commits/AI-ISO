"""Tests for :class:`app.services.compliance.ComplianceService`."""

from __future__ import annotations

from shared_core.events.base import DomainEvent
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ComplianceStatus, ComplianceType
from app.repositories.asset_compliance import AssetComplianceRepository
from app.repositories.managed_asset import ManagedAssetRepository
from app.services.compliance import ComplianceService, EventPublisher, _worst
from tests.conftest import make_managed_asset


def test_worst_with_no_statuses_returns_unknown() -> None:
    assert _worst([]) == ComplianceStatus.UNKNOWN


def _build(
    db_session: AsyncSession, *, publish_event: EventPublisher | None = None
) -> ComplianceService:
    return ComplianceService(
        AssetComplianceRepository(db_session),
        ManagedAssetRepository(db_session),
        publish_event=publish_event,
    )


async def test_evaluate_compliant_updates_aggregate(db_session: AsyncSession) -> None:
    managed_asset = await make_managed_asset(db_session)
    service = _build(db_session)

    await service.evaluate(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        compliance_type=ComplianceType.SECURITY,
        status=ComplianceStatus.COMPLIANT,
        details={},
        exception_reason=None,
    )

    assert managed_asset.compliance_status == ComplianceStatus.COMPLIANT


async def test_evaluate_non_compliant_without_publisher_configured(
    db_session: AsyncSession,
) -> None:
    """No ``publish_event`` callback configured -- the NON_COMPLIANT
    path must still complete without attempting to call ``None``.
    """
    managed_asset = await make_managed_asset(db_session)
    service = _build(db_session)

    await service.evaluate(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        compliance_type=ComplianceType.SECURITY,
        status=ComplianceStatus.NON_COMPLIANT,
        details={},
        exception_reason=None,
    )

    assert managed_asset.compliance_status == ComplianceStatus.NON_COMPLIANT


async def test_evaluate_non_compliant_publishes_event_and_sets_worst(
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
        compliance_type=ComplianceType.SECURITY,
        status=ComplianceStatus.COMPLIANT,
        details={},
        exception_reason=None,
    )
    await service.evaluate(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        compliance_type=ComplianceType.PATCH,
        status=ComplianceStatus.NON_COMPLIANT,
        details={"reason": "missing patches"},
        exception_reason=None,
    )

    assert managed_asset.compliance_status == ComplianceStatus.NON_COMPLIANT
    assert any(event.event_name == "ComplianceFailed" for event in published)


async def test_list_for_managed_asset_filters_by_type(db_session: AsyncSession) -> None:
    managed_asset = await make_managed_asset(db_session)
    service = _build(db_session)
    await service.evaluate(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        compliance_type=ComplianceType.LICENSE,
        status=ComplianceStatus.COMPLIANT,
        details={},
        exception_reason=None,
    )
    await service.evaluate(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        compliance_type=ComplianceType.CONFIGURATION,
        status=ComplianceStatus.EXCEPTION,
        details={},
        exception_reason="Approved deviation",
    )

    license_only = await service.list_for_managed_asset(
        managed_asset.id, compliance_type=ComplianceType.LICENSE
    )
    assert len(license_only) == 1
    assert license_only[0].compliance_type == ComplianceType.LICENSE
