"""Tests for :class:`app.services.warranty.WarrantyService`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from shared_core.events.base import DomainEvent
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import RenewalStatus, WarrantyStatus
from app.repositories.asset_warranty import AssetWarrantyRepository
from app.repositories.managed_asset import ManagedAssetRepository
from app.services.warranty import EventPublisher, WarrantyService
from tests.conftest import make_managed_asset


def _build(
    db_session: AsyncSession, *, publish_event: EventPublisher | None = None
) -> WarrantyService:
    return WarrantyService(
        AssetWarrantyRepository(db_session),
        ManagedAssetRepository(db_session),
        publish_event=publish_event,
    )


async def test_update_creates_warranty_and_sets_active_status(db_session: AsyncSession) -> None:
    managed_asset = await make_managed_asset(db_session)
    service = _build(db_session)
    now = datetime.now(UTC)

    warranty = await service.update(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        provider="Acme Support",
        warranty_number="W-123",
        coverage="Full hardware coverage",
        start_date=now,
        end_date=now + timedelta(days=365),
        renewal_status=RenewalStatus.NOT_RENEWED,
    )

    assert warranty.provider == "Acme Support"
    assert managed_asset.warranty_status == WarrantyStatus.ACTIVE


async def test_update_sets_expiring_soon_status(db_session: AsyncSession) -> None:
    managed_asset = await make_managed_asset(db_session)
    service = _build(db_session)
    now = datetime.now(UTC)

    await service.update(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        provider="Acme Support",
        warranty_number=None,
        coverage=None,
        start_date=now - timedelta(days=300),
        end_date=now + timedelta(days=10),
        renewal_status=RenewalStatus.PENDING,
    )

    assert managed_asset.warranty_status == WarrantyStatus.EXPIRING_SOON


async def test_update_sets_expired_status(db_session: AsyncSession) -> None:
    managed_asset = await make_managed_asset(db_session)
    service = _build(db_session)
    now = datetime.now(UTC)

    await service.update(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        provider="Acme Support",
        warranty_number=None,
        coverage=None,
        start_date=now - timedelta(days=400),
        end_date=now - timedelta(days=10),
        renewal_status=RenewalStatus.DECLINED,
    )

    assert managed_asset.warranty_status == WarrantyStatus.EXPIRED


async def test_get_current_returns_none_when_absent(db_session: AsyncSession) -> None:
    managed_asset = await make_managed_asset(db_session)
    service = _build(db_session)
    assert await service.get_current(managed_asset.id) is None


async def test_update_same_end_date_updates_in_place(db_session: AsyncSession) -> None:
    managed_asset = await make_managed_asset(db_session)
    service = _build(db_session)
    now = datetime.now(UTC)
    end_date = now + timedelta(days=365)

    first = await service.update(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        provider="Acme Support",
        warranty_number=None,
        coverage=None,
        start_date=now,
        end_date=end_date,
        renewal_status=RenewalStatus.NOT_RENEWED,
    )
    second = await service.update(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        provider="Beta Support",
        warranty_number="W-2",
        coverage="Extended",
        start_date=now,
        end_date=end_date,
        renewal_status=RenewalStatus.RENEWED,
    )

    assert first.id == second.id
    assert second.provider == "Beta Support"
    assert second.warranty_number == "W-2"

    periods = await service.list_for_managed_asset(managed_asset.id)
    assert len(periods) == 1


async def test_add_claim_raises_not_found_when_no_warranty(db_session: AsyncSession) -> None:
    managed_asset = await make_managed_asset(db_session)
    service = _build(db_session)
    with pytest.raises(NotFoundError):
        await service.add_claim(managed_asset.id, description="n/a", outcome="n/a")


async def test_add_claim_appends_to_list(db_session: AsyncSession) -> None:
    managed_asset = await make_managed_asset(db_session)
    service = _build(db_session)
    now = datetime.now(UTC)
    await service.update(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        provider="Acme Support",
        warranty_number=None,
        coverage=None,
        start_date=now,
        end_date=now + timedelta(days=365),
        renewal_status=RenewalStatus.NOT_RENEWED,
    )

    warranty = await service.add_claim(
        managed_asset.id, description="Screen replacement", outcome="approved"
    )

    assert len(warranty.claims) == 1
    assert warranty.claims[0]["description"] == "Screen replacement"


async def test_sweep_expiring_publishes_and_marks_alerted(db_session: AsyncSession) -> None:
    published: list[DomainEvent] = []

    async def _publish(event: DomainEvent) -> None:
        published.append(event)

    managed_asset = await make_managed_asset(db_session)
    service = _build(db_session, publish_event=_publish)
    now = datetime.now(UTC)
    await service.update(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        provider="Acme Support",
        warranty_number=None,
        coverage=None,
        start_date=now - timedelta(days=350),
        end_date=now + timedelta(days=5),
        renewal_status=RenewalStatus.NOT_RENEWED,
    )

    count = await service.sweep_expiring(within_days=30)

    assert count == 1
    assert any(event.event_name == "WarrantyExpired" for event in published)

    second_pass = await service.sweep_expiring(within_days=30)
    assert second_pass == 0
