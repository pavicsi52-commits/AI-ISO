"""Tests for :class:`app.services.contract.ContractService`."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from shared_core.events.base import DomainEvent
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ContractStatus, ContractType
from app.repositories.asset_contract import AssetContractRepository
from app.repositories.asset_vendor import AssetVendorRepository
from app.services.contract import ContractService, EventPublisher
from tests.conftest import make_managed_asset


def _build(
    db_session: AsyncSession, *, publish_event: EventPublisher | None = None
) -> ContractService:
    return ContractService(
        AssetContractRepository(db_session),
        AssetVendorRepository(db_session),
        publish_event=publish_event,
    )


async def test_create_contract(db_session: AsyncSession) -> None:
    managed_asset = await make_managed_asset(db_session)
    service = _build(db_session)
    now = datetime.now(UTC)

    contract = await service.create(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        vendor_id=None,
        contract_type=ContractType.SUPPORT,
        contract_number="C-1",
        start_date=now,
        end_date=now + timedelta(days=365),
        documents=[],
    )

    assert contract.contract_type == ContractType.SUPPORT
    assert contract.status == ContractStatus.ACTIVE


async def test_get_or_create_vendor_is_idempotent(db_session: AsyncSession) -> None:
    org_id = uuid.uuid4()
    service = _build(db_session)

    first = await service.get_or_create_vendor(org_id, name="Acme Corp")
    second = await service.get_or_create_vendor(org_id, name="Acme Corp")

    assert first.id == second.id

    vendors = await service.list_vendors(org_id)
    assert len(vendors) == 1


async def test_sweep_expiring_publishes_and_marks_expired(db_session: AsyncSession) -> None:
    published: list[DomainEvent] = []

    async def _publish(event: DomainEvent) -> None:
        published.append(event)

    managed_asset = await make_managed_asset(db_session)
    service = _build(db_session, publish_event=_publish)
    now = datetime.now(UTC)

    await service.create(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        vendor_id=None,
        contract_type=ContractType.MAINTENANCE,
        contract_number=None,
        start_date=now - timedelta(days=350),
        end_date=now + timedelta(days=5),
        documents=[],
    )

    count = await service.sweep_expiring(within_days=30)

    assert count == 1
    assert any(event.event_name == "ContractExpired" for event in published)

    contracts = await service.list_for_managed_asset(managed_asset.id)
    assert contracts[0].status == ContractStatus.EXPIRED


async def test_sweep_expiring_without_publisher_configured(db_session: AsyncSession) -> None:
    managed_asset = await make_managed_asset(db_session)
    service = _build(db_session)
    now = datetime.now(UTC)
    await service.create(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        vendor_id=None,
        contract_type=ContractType.LICENSE,
        contract_number=None,
        start_date=now - timedelta(days=350),
        end_date=now + timedelta(days=5),
        documents=[],
    )

    count = await service.sweep_expiring(within_days=30)
    assert count == 1
