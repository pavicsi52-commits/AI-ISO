"""Tests for :class:`AssetService`, the core orchestrator."""

from __future__ import annotations

import uuid

import pytest
from shared_core.events.base import DomainEvent
from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_location import AssetLocation
from app.models.enums import AssetStatus, AssetType, Criticality, HealthStatus, LifecycleState
from app.repositories.asset_health_history import AssetHealthHistoryRepository
from app.repositories.asset_history import AssetHistoryRepository
from app.repositories.asset_lifecycle_history import AssetLifecycleHistoryRepository
from app.repositories.asset_status_history import AssetStatusHistoryRepository
from app.repositories.asset_tag import AssetTagRepository
from app.repositories.asset_version import AssetVersionRepository
from app.repositories.inventory_audit import InventoryAuditRepository
from app.topology.graph import TopologyGraphClient
from tests.conftest import build_asset_service


def _create_kwargs(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "organization_id": uuid.uuid4(),
        "project_id": None,
        "name": "web-01",
        "display_name": None,
        "hostname": "web-01.internal",
        "fqdn": None,
        "ip_address": None,
        "mac_address": None,
        "serial_number": None,
        "vendor": None,
        "manufacturer": None,
        "model": None,
        "firmware_version": None,
        "operating_system": None,
        "architecture": None,
        "environment": None,
        "asset_type": AssetType.VIRTUAL_MACHINE,
        "category_id": None,
        "class_id": None,
        "location_id": None,
        "owner_id": None,
        "criticality": Criticality.MEDIUM,
        "metadata": {},
        "tags": [],
        "created_by": None,
    }
    base.update(overrides)
    return base


def _update_kwargs(asset_id: uuid.UUID, **overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "asset_id": asset_id,
        "actor_id": None,
        "name": "web-01",
        "display_name": None,
        "hostname": "web-01.internal",
        "fqdn": None,
        "ip_address": None,
        "mac_address": None,
        "serial_number": None,
        "vendor": None,
        "manufacturer": None,
        "model": None,
        "firmware_version": None,
        "operating_system": None,
        "architecture": None,
        "environment": None,
        "category_id": None,
        "class_id": None,
        "location_id": None,
        "owner_id": None,
        "status": AssetStatus.DISCOVERED,
        "health": HealthStatus.UNKNOWN,
        "lifecycle_state": LifecycleState.PLANNED,
        "criticality": Criticality.MEDIUM,
        "metadata": {},
    }
    base.update(overrides)
    return base


async def test_create_records_history_audit_tags_and_publishes(
    db_session: AsyncSession, topology_graph_client: TopologyGraphClient
) -> None:
    published: list[DomainEvent] = []

    async def _publish(event: DomainEvent) -> None:
        published.append(event)

    service = build_asset_service(db_session, topology_graph_client, publish_event=_publish)
    asset = await service.create(**_create_kwargs(tags=["prod", "web"]))  # type: ignore[arg-type]

    assert asset.status == AssetStatus.DISCOVERED
    assert asset.health == HealthStatus.UNKNOWN
    assert asset.lifecycle_state == LifecycleState.PLANNED
    assert asset.current_version == 1

    versions = await AssetVersionRepository(db_session).list_for_asset(asset.id)
    assert len(versions) == 1

    tags = await AssetTagRepository(db_session).list_for_asset(asset.id)
    assert {t.label for t in tags} == {"prod", "web"}

    history = await AssetHistoryRepository(db_session).list_for_asset(asset.id)
    assert len(history) == 1

    audit = await InventoryAuditRepository(db_session).list_for_asset(asset.id)
    assert len(audit) == 1

    assert len(published) == 1
    assert published[0].event_name == "AssetCreated"


async def test_create_duplicate_hostname_conflicts(
    db_session: AsyncSession, topology_graph_client: TopologyGraphClient
) -> None:
    service = build_asset_service(db_session, topology_graph_client)
    org_id = uuid.uuid4()
    await service.create(**_create_kwargs(organization_id=org_id, hostname="dup.internal"))  # type: ignore[arg-type]
    with pytest.raises(ConflictError):
        await service.create(
            **_create_kwargs(organization_id=org_id, name="other", hostname="dup.internal")  # type: ignore[arg-type]
        )


async def test_create_duplicate_serial_number_conflicts(
    db_session: AsyncSession, topology_graph_client: TopologyGraphClient
) -> None:
    service = build_asset_service(db_session, topology_graph_client)
    org_id = uuid.uuid4()
    await service.create(
        **_create_kwargs(organization_id=org_id, hostname=None, serial_number="SN-1")  # type: ignore[arg-type]
    )
    with pytest.raises(ConflictError):
        await service.create(
            **_create_kwargs(
                organization_id=org_id, name="other", hostname=None, serial_number="SN-1"
            )  # type: ignore[arg-type]
        )


async def test_create_duplicate_mac_address_conflicts(
    db_session: AsyncSession, topology_graph_client: TopologyGraphClient
) -> None:
    service = build_asset_service(db_session, topology_graph_client)
    org_id = uuid.uuid4()
    await service.create(
        **_create_kwargs(organization_id=org_id, hostname=None, mac_address="AA:BB:CC")  # type: ignore[arg-type]
    )
    with pytest.raises(ConflictError):
        await service.create(
            **_create_kwargs(
                organization_id=org_id, name="other", hostname=None, mac_address="AA:BB:CC"
            )  # type: ignore[arg-type]
        )


async def test_duplicate_identifier_allowed_in_different_org(
    db_session: AsyncSession, topology_graph_client: TopologyGraphClient
) -> None:
    service = build_asset_service(db_session, topology_graph_client)
    await service.create(**_create_kwargs(hostname="shared.internal"))  # type: ignore[arg-type]
    asset = await service.create(**_create_kwargs(hostname="shared.internal"))  # type: ignore[arg-type]
    assert asset.hostname == "shared.internal"


async def test_get_by_id_not_found(
    db_session: AsyncSession, topology_graph_client: TopologyGraphClient
) -> None:
    service = build_asset_service(db_session, topology_graph_client)
    with pytest.raises(NotFoundError):
        await service.get_by_id(uuid.uuid4())


async def test_list_for_org(
    db_session: AsyncSession, topology_graph_client: TopologyGraphClient
) -> None:
    service = build_asset_service(db_session, topology_graph_client)
    org_id = uuid.uuid4()
    await service.create(**_create_kwargs(organization_id=org_id))  # type: ignore[arg-type]
    await service.create(**_create_kwargs(organization_id=org_id, name="second", hostname=None))  # type: ignore[arg-type]
    records = await service.list_for_org(org_id)
    assert len(records) == 2


async def test_update_records_status_health_lifecycle_changes_and_publishes(
    db_session: AsyncSession, topology_graph_client: TopologyGraphClient
) -> None:
    published: list[DomainEvent] = []

    async def _publish(event: DomainEvent) -> None:
        published.append(event)

    service = build_asset_service(db_session, topology_graph_client, publish_event=_publish)
    asset = await service.create(**_create_kwargs())  # type: ignore[arg-type]
    published.clear()

    updated = await service.update(
        **_update_kwargs(  # type: ignore[arg-type]
            asset.id,
            status=AssetStatus.MANAGED,
            health=HealthStatus.HEALTHY,
            lifecycle_state=LifecycleState.OPERATIONAL,
            owner_id=uuid.uuid4(),
            location_id=None,
        )
    )
    assert updated.status == AssetStatus.MANAGED
    assert updated.current_version == 2

    status_history = await AssetStatusHistoryRepository(db_session).list_for_asset(asset.id)
    assert len(status_history) == 1
    health_history = await AssetHealthHistoryRepository(db_session).list_for_asset(asset.id)
    assert len(health_history) == 1
    lifecycle_history = await AssetLifecycleHistoryRepository(db_session).list_for_asset(asset.id)
    assert len(lifecycle_history) == 1

    event_names = {event.event_name for event in published}
    assert {"AssetHealthChanged", "AssetOwnerChanged", "AssetUpdated"} <= event_names


async def test_update_no_change_records_no_transition_history(
    db_session: AsyncSession, topology_graph_client: TopologyGraphClient
) -> None:
    service = build_asset_service(db_session, topology_graph_client)
    asset = await service.create(**_create_kwargs())  # type: ignore[arg-type]
    await service.update(**_update_kwargs(asset.id))  # type: ignore[arg-type]

    assert await AssetStatusHistoryRepository(db_session).list_for_asset(asset.id) == []
    assert await AssetHealthHistoryRepository(db_session).list_for_asset(asset.id) == []
    assert await AssetLifecycleHistoryRepository(db_session).list_for_asset(asset.id) == []


async def test_update_location_change_publishes_moved_event(
    db_session: AsyncSession, topology_graph_client: TopologyGraphClient
) -> None:
    published: list[DomainEvent] = []

    async def _publish(event: DomainEvent) -> None:
        published.append(event)

    service = build_asset_service(db_session, topology_graph_client, publish_event=_publish)
    asset = await service.create(**_create_kwargs())  # type: ignore[arg-type]
    published.clear()

    location = AssetLocation(organization_id=asset.organization_id, name="DC1")
    db_session.add(location)
    await db_session.flush()

    await service.update(**_update_kwargs(asset.id, location_id=location.id))  # type: ignore[arg-type]
    event_names = {event.event_name for event in published}
    assert "AssetMoved" in event_names


async def test_delete_removes_and_publishes(
    db_session: AsyncSession, topology_graph_client: TopologyGraphClient
) -> None:
    published: list[DomainEvent] = []

    async def _publish(event: DomainEvent) -> None:
        published.append(event)

    service = build_asset_service(db_session, topology_graph_client, publish_event=_publish)
    asset = await service.create(**_create_kwargs())  # type: ignore[arg-type]
    published.clear()

    await service.delete(asset.id, actor_id=uuid.uuid4())
    with pytest.raises(NotFoundError):
        await service.get_by_id(asset.id)
    assert any(event.event_name == "AssetDeleted" for event in published)


async def test_search(db_session: AsyncSession, topology_graph_client: TopologyGraphClient) -> None:
    service = build_asset_service(db_session, topology_graph_client)
    org_id = uuid.uuid4()
    await service.create(
        **_create_kwargs(organization_id=org_id, name="alpha", hostname="alpha.internal")  # type: ignore[arg-type]
    )
    await service.create(
        **_create_kwargs(organization_id=org_id, name="beta", hostname="beta.internal")  # type: ignore[arg-type]
    )

    result = await service.search(
        query="alpha", filters=None, sort_fields=None, page=1, page_size=20
    )
    assert result.metadata.total == 1
    assert result.items[0].name == "alpha"


__all__: list[str] = []
