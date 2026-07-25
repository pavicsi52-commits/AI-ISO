"""Tests for :class:`app.services.ownership.OwnershipService`."""

from __future__ import annotations

import uuid

from shared_core.events.base import DomainEvent
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ContactRole, OwnerRole
from app.repositories.asset_contact import AssetContactRepository
from app.repositories.asset_owner import AssetOwnerRepository
from app.services.ownership import EventPublisher, OwnershipService
from tests.conftest import make_managed_asset


def _build(
    db_session: AsyncSession, *, publish_event: EventPublisher | None = None
) -> OwnershipService:
    return OwnershipService(
        AssetOwnerRepository(db_session),
        AssetContactRepository(db_session),
        publish_event=publish_event,
    )


async def test_transfer_creates_owner(db_session: AsyncSession) -> None:
    managed_asset = await make_managed_asset(db_session)
    service = _build(db_session)
    principal_id = uuid.uuid4()

    owner = await service.transfer(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        role=OwnerRole.BUSINESS_OWNER,
        principal_id=principal_id,
        name=None,
    )

    assert owner.role == OwnerRole.BUSINESS_OWNER
    assert owner.principal_id == principal_id


async def test_transfer_publishes_event(db_session: AsyncSession) -> None:
    published: list[DomainEvent] = []

    async def _publish(event: DomainEvent) -> None:
        published.append(event)

    managed_asset = await make_managed_asset(db_session)
    service = _build(db_session, publish_event=_publish)

    await service.transfer(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        role=OwnerRole.TECHNICAL_OWNER,
        principal_id=uuid.uuid4(),
        name=None,
    )

    assert any(event.event_name == "OwnershipTransferred" for event in published)


async def test_transfer_replaces_existing_role_holder(db_session: AsyncSession) -> None:
    managed_asset = await make_managed_asset(db_session)
    service = _build(db_session)
    first_principal = uuid.uuid4()
    second_principal = uuid.uuid4()

    first = await service.transfer(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        role=OwnerRole.SUPPORT_TEAM,
        principal_id=first_principal,
        name=None,
    )
    second = await service.transfer(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        role=OwnerRole.SUPPORT_TEAM,
        principal_id=second_principal,
        name=None,
    )

    assert first.id == second.id
    assert second.principal_id == second_principal

    owners = await service.list_owners(managed_asset.id)
    assert len(owners) == 1


async def test_assign_contact_creates_and_replaces(db_session: AsyncSession) -> None:
    managed_asset = await make_managed_asset(db_session)
    service = _build(db_session)

    created = await service.assign_contact(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        role=ContactRole.VENDOR_CONTACT,
        name="Jane Vendor",
        email="jane@vendor.example",
        phone=None,
    )
    replaced = await service.assign_contact(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        role=ContactRole.VENDOR_CONTACT,
        name="John Vendor",
        email="john@vendor.example",
        phone=None,
    )

    assert created.id == replaced.id
    assert replaced.name == "John Vendor"

    contacts = await service.list_contacts(managed_asset.id)
    assert len(contacts) == 1
