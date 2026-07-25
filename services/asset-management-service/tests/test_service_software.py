"""Tests for :class:`app.services.software.SoftwareService`."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import AuditOutcome, SoftwareEndOfLifeStatus
from app.repositories.asset_patch_history import AssetPatchHistoryRepository
from app.repositories.asset_software import AssetSoftwareRepository
from app.services.software import SoftwareService
from tests.conftest import make_managed_asset


def _build(db_session: AsyncSession) -> SoftwareService:
    return SoftwareService(
        AssetSoftwareRepository(db_session), AssetPatchHistoryRepository(db_session)
    )


async def test_install_and_list(db_session: AsyncSession) -> None:
    managed_asset = await make_managed_asset(db_session)
    service = _build(db_session)

    software = await service.install(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        name="nginx",
        software_version="1.25.0",
        license_key=None,
        end_of_life_status=SoftwareEndOfLifeStatus.SUPPORTED,
        installed_at=datetime.now(UTC),
    )

    assert software.name == "nginx"
    records = await service.list_for_managed_asset(managed_asset.id)
    assert len(records) == 1


async def test_record_patch_and_list_history(db_session: AsyncSession) -> None:
    managed_asset = await make_managed_asset(db_session)
    service = _build(db_session)
    software = await service.install(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        name="openssl",
        software_version="3.0.0",
        license_key=None,
        end_of_life_status=SoftwareEndOfLifeStatus.SUPPORTED,
        installed_at=None,
    )

    patch = await service.record_patch(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        software_id=software.id,
        patch_name="CVE-2026-0001 fix",
        applied_at=datetime.now(UTC),
        outcome=AuditOutcome.SUCCESS,
        notes=None,
    )

    assert patch.software_id == software.id
    history = await service.list_patch_history(managed_asset.id)
    assert len(history) == 1
    assert history[0].outcome == AuditOutcome.SUCCESS
