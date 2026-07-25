"""Tests for :class:`app.services.firmware.FirmwareService`."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ComplianceStatus
from app.repositories.asset_firmware import AssetFirmwareRepository
from app.services.firmware import FirmwareService
from app.services.lifecycle import LifecycleService
from tests.conftest import build_lifecycle_service, make_managed_asset


def _build(db_session: AsyncSession) -> tuple[FirmwareService, LifecycleService]:
    lifecycle = build_lifecycle_service(db_session)
    return FirmwareService(AssetFirmwareRepository(db_session), lifecycle), lifecycle


async def test_upsert_creates_firmware_record(db_session: AsyncSession) -> None:
    managed_asset = await make_managed_asset(db_session)
    service, lifecycle = _build(db_session)

    firmware = await service.upsert(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        actor_id=None,
        current_version="1.0.0",
        available_version=None,
        compliance_status=ComplianceStatus.COMPLIANT,
        vendor_recommendation=None,
    )

    assert firmware.current_version == "1.0.0"
    history = await lifecycle.list_history(managed_asset.id)
    assert any(entry.event_type == "firmware_installed" for entry in history)


async def test_upsert_records_upgrade_history_on_version_change(db_session: AsyncSession) -> None:
    managed_asset = await make_managed_asset(db_session)
    service, lifecycle = _build(db_session)
    await service.upsert(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        actor_id=None,
        current_version="1.0.0",
        available_version="1.1.0",
        compliance_status=ComplianceStatus.COMPLIANT,
        vendor_recommendation=None,
    )

    upgraded = await service.upsert(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        actor_id=None,
        current_version="1.1.0",
        available_version=None,
        compliance_status=ComplianceStatus.COMPLIANT,
        vendor_recommendation=None,
    )

    assert upgraded.current_version == "1.1.0"
    history = await lifecycle.list_history(managed_asset.id)
    assert any(entry.event_type == "firmware_upgraded" for entry in history)


async def test_upsert_no_history_when_version_unchanged(db_session: AsyncSession) -> None:
    managed_asset = await make_managed_asset(db_session)
    service, lifecycle = _build(db_session)
    await service.upsert(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        actor_id=None,
        current_version="1.0.0",
        available_version=None,
        compliance_status=ComplianceStatus.COMPLIANT,
        vendor_recommendation=None,
    )
    await service.upsert(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        actor_id=None,
        current_version="1.0.0",
        available_version=None,
        compliance_status=ComplianceStatus.NON_COMPLIANT,
        vendor_recommendation="Patch now",
    )

    history = await lifecycle.list_history(managed_asset.id)
    assert len(history) == 1


async def test_get_for_managed_asset_returns_none_when_absent(db_session: AsyncSession) -> None:
    managed_asset = await make_managed_asset(db_session)
    service, _lifecycle = _build(db_session)
    assert await service.get_for_managed_asset(managed_asset.id) is None
