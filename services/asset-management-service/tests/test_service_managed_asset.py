"""Tests for :class:`app.services.managed_asset.ManagedAssetService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.events.base import DomainEvent
from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import Criticality, LifecycleState, ManagedAssetStatus
from tests.conftest import build_managed_asset_service, make_managed_asset


async def test_create_registers_managed_asset(db_session: AsyncSession) -> None:
    service = build_managed_asset_service(db_session)
    org_id = uuid.uuid4()
    inventory_asset_id = uuid.uuid4()

    managed_asset = await service.create(
        organization_id=org_id,
        project_id=None,
        inventory_asset_id=inventory_asset_id,
        business_name="Payments API",
        business_owner_id=None,
        technical_owner_id=None,
        support_team_id=None,
        vendor_id=None,
        criticality=Criticality.HIGH,
        acquisition_date=None,
        metadata={},
        tags=[],
        labels={},
        created_by=uuid.uuid4(),
    )

    assert managed_asset.business_name == "Payments API"
    assert managed_asset.status == ManagedAssetStatus.PLANNED
    assert managed_asset.lifecycle_state == LifecycleState.PROVISIONING
    assert managed_asset.criticality == Criticality.HIGH

    fetched = await service.get_by_id(managed_asset.id)
    assert fetched.id == managed_asset.id


async def test_create_publishes_event(db_session: AsyncSession) -> None:
    published: list[DomainEvent] = []

    async def _publish(event: DomainEvent) -> None:
        published.append(event)

    service = build_managed_asset_service(db_session, publish_event=_publish)
    await service.create(
        organization_id=uuid.uuid4(),
        project_id=None,
        inventory_asset_id=uuid.uuid4(),
        business_name="Order Service",
        business_owner_id=None,
        technical_owner_id=None,
        support_team_id=None,
        vendor_id=None,
        criticality=Criticality.MEDIUM,
        acquisition_date=None,
        metadata={},
        tags=[],
        labels={},
        created_by=None,
    )

    assert any(event.event_name == "ManagedAssetCreated" for event in published)


async def test_create_rejects_duplicate_inventory_asset(db_session: AsyncSession) -> None:
    service = build_managed_asset_service(db_session)
    inventory_asset_id = uuid.uuid4()
    org_id = uuid.uuid4()
    await service.create(
        organization_id=org_id,
        project_id=None,
        inventory_asset_id=inventory_asset_id,
        business_name="First",
        business_owner_id=None,
        technical_owner_id=None,
        support_team_id=None,
        vendor_id=None,
        criticality=Criticality.LOW,
        acquisition_date=None,
        metadata={},
        tags=[],
        labels={},
        created_by=None,
    )

    with pytest.raises(ConflictError):
        await service.create(
            organization_id=org_id,
            project_id=None,
            inventory_asset_id=inventory_asset_id,
            business_name="Second",
            business_owner_id=None,
            technical_owner_id=None,
            support_team_id=None,
            vendor_id=None,
            criticality=Criticality.LOW,
            acquisition_date=None,
            metadata={},
            tags=[],
            labels={},
            created_by=None,
        )


async def test_get_by_id_raises_not_found(db_session: AsyncSession) -> None:
    service = build_managed_asset_service(db_session)
    with pytest.raises(NotFoundError):
        await service.get_by_id(uuid.uuid4())


async def test_get_by_inventory_asset_id_returns_none_when_missing(
    db_session: AsyncSession,
) -> None:
    service = build_managed_asset_service(db_session)
    assert await service.get_by_inventory_asset_id(uuid.uuid4()) is None


async def test_list_for_org(db_session: AsyncSession) -> None:
    org_id = uuid.uuid4()
    await make_managed_asset(db_session, organization_id=org_id)
    await make_managed_asset(db_session, organization_id=org_id)
    await make_managed_asset(db_session, organization_id=uuid.uuid4())

    service = build_managed_asset_service(db_session)
    records = await service.list_for_org(org_id)
    assert len(records) == 2


async def test_update_publishes_lifecycle_changed_on_transition(db_session: AsyncSession) -> None:
    published: list[DomainEvent] = []

    async def _publish(event: DomainEvent) -> None:
        published.append(event)

    managed_asset = await make_managed_asset(db_session)
    service = build_managed_asset_service(db_session, publish_event=_publish)

    updated = await service.update(
        managed_asset.id,
        actor_id=uuid.uuid4(),
        business_name=managed_asset.business_name,
        business_owner_id=None,
        technical_owner_id=None,
        support_team_id=None,
        vendor_id=None,
        status=ManagedAssetStatus.OPERATIONAL,
        lifecycle_state=LifecycleState.OPERATIONAL,
        criticality=managed_asset.criticality,
        acquisition_date=None,
        retirement_date=None,
        metadata={},
        tags=[],
        labels={},
    )

    assert updated.lifecycle_state == LifecycleState.OPERATIONAL
    assert any(event.event_name == "LifecycleChanged" for event in published)


async def test_update_no_event_when_lifecycle_unchanged(db_session: AsyncSession) -> None:
    published: list[DomainEvent] = []

    async def _publish(event: DomainEvent) -> None:
        published.append(event)

    managed_asset = await make_managed_asset(db_session, lifecycle_state=LifecycleState.OPERATIONAL)
    service = build_managed_asset_service(db_session, publish_event=_publish)

    await service.update(
        managed_asset.id,
        actor_id=None,
        business_name="Renamed",
        business_owner_id=None,
        technical_owner_id=None,
        support_team_id=None,
        vendor_id=None,
        status=managed_asset.status,
        lifecycle_state=LifecycleState.OPERATIONAL,
        criticality=managed_asset.criticality,
        acquisition_date=None,
        retirement_date=None,
        metadata={},
        tags=[],
        labels={},
    )

    assert not any(event.event_name == "LifecycleChanged" for event in published)


async def test_delete_soft_deletes(db_session: AsyncSession) -> None:
    managed_asset = await make_managed_asset(db_session)
    service = build_managed_asset_service(db_session)

    await service.delete(managed_asset.id, actor_id=uuid.uuid4())

    with pytest.raises(NotFoundError):
        await service.get_by_id(managed_asset.id)


async def test_search(db_session: AsyncSession) -> None:
    org_id = uuid.uuid4()
    await make_managed_asset(db_session, organization_id=org_id, business_name="Payments API")
    await make_managed_asset(db_session, organization_id=org_id, business_name="Order Service")

    service = build_managed_asset_service(db_session)
    result = await service.search(
        query="Payments", filters=None, sort_fields=None, page=1, page_size=10
    )
    assert result.metadata.total == 1
    assert result.items[0].business_name == "Payments API"
