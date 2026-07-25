"""Tests for :class:`AssetRelationshipService`, including its Neo4j sync."""

from __future__ import annotations

import uuid

import pytest
from shared_core.events.base import DomainEvent
from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Asset
from app.models.enums import RelationshipType
from app.repositories.asset_relationship import AssetRelationshipRepository
from app.repositories.asset_topology_cache import AssetTopologyCacheRepository
from app.services.relationship import AssetRelationshipService
from app.services.topology import TopologyService
from app.topology.graph import TopologyGraphClient
from tests.conftest import make_asset


def _service(db_session: AsyncSession, graph: TopologyGraphClient) -> AssetRelationshipService:
    topology = TopologyService(graph, AssetTopologyCacheRepository(db_session))
    return AssetRelationshipService(AssetRelationshipRepository(db_session), topology)


async def _sync_node(graph: TopologyGraphClient, asset: Asset) -> None:
    await graph.upsert_asset_node(
        asset.id,
        organization_id=asset.organization_id,
        asset_type=str(asset.asset_type),
        name=asset.name,
    )


async def test_create_and_list(
    db_session: AsyncSession, topology_graph_client: TopologyGraphClient
) -> None:
    source = await make_asset(db_session, name="source")
    target = await make_asset(db_session, name="target", organization_id=source.organization_id)
    await _sync_node(topology_graph_client, source)
    await _sync_node(topology_graph_client, target)

    service = _service(db_session, topology_graph_client)
    relationship = await service.create(
        organization_id=source.organization_id,
        source_asset_id=source.id,
        target_asset_id=target.id,
        relationship_type=RelationshipType.DEPENDS_ON,
    )
    assert relationship.relationship_type == RelationshipType.DEPENDS_ON

    records = await service.list_for_asset(source.id)
    assert [r.id for r in records] == [relationship.id]
    records_from_target = await service.list_for_asset(target.id)
    assert [r.id for r in records_from_target] == [relationship.id]

    neighbors = await topology_graph_client.get_neighbors(source.id)
    assert len(neighbors) == 1


async def test_create_publishes_event(
    db_session: AsyncSession, topology_graph_client: TopologyGraphClient
) -> None:
    published: list[DomainEvent] = []

    async def _publish(event: DomainEvent) -> None:
        published.append(event)

    source = await make_asset(db_session, name="source")
    target = await make_asset(db_session, name="target", organization_id=source.organization_id)
    await _sync_node(topology_graph_client, source)
    await _sync_node(topology_graph_client, target)

    topology = TopologyService(topology_graph_client, AssetTopologyCacheRepository(db_session))
    service = AssetRelationshipService(
        AssetRelationshipRepository(db_session), topology, publish_event=_publish
    )
    await service.create(
        organization_id=source.organization_id,
        source_asset_id=source.id,
        target_asset_id=target.id,
        relationship_type=RelationshipType.RUNS_ON,
    )
    assert len(published) == 1
    assert published[0].event_name == "RelationshipCreated"


async def test_create_duplicate_edge_conflicts(
    db_session: AsyncSession, topology_graph_client: TopologyGraphClient
) -> None:
    source = await make_asset(db_session, name="source")
    target = await make_asset(db_session, name="target", organization_id=source.organization_id)
    await _sync_node(topology_graph_client, source)
    await _sync_node(topology_graph_client, target)

    service = _service(db_session, topology_graph_client)
    await service.create(
        organization_id=source.organization_id,
        source_asset_id=source.id,
        target_asset_id=target.id,
        relationship_type=RelationshipType.DEPENDS_ON,
    )
    with pytest.raises(ConflictError):
        await service.create(
            organization_id=source.organization_id,
            source_asset_id=source.id,
            target_asset_id=target.id,
            relationship_type=RelationshipType.DEPENDS_ON,
        )


async def test_delete_not_found(
    db_session: AsyncSession, topology_graph_client: TopologyGraphClient
) -> None:
    service = _service(db_session, topology_graph_client)
    with pytest.raises(NotFoundError):
        await service.delete(uuid.uuid4())


async def test_delete_removes_edge_and_publishes(
    db_session: AsyncSession, topology_graph_client: TopologyGraphClient
) -> None:
    published: list[DomainEvent] = []

    async def _publish(event: DomainEvent) -> None:
        published.append(event)

    source = await make_asset(db_session, name="source")
    target = await make_asset(db_session, name="target", organization_id=source.organization_id)
    await _sync_node(topology_graph_client, source)
    await _sync_node(topology_graph_client, target)

    topology = TopologyService(topology_graph_client, AssetTopologyCacheRepository(db_session))
    service = AssetRelationshipService(
        AssetRelationshipRepository(db_session), topology, publish_event=_publish
    )
    relationship = await service.create(
        organization_id=source.organization_id,
        source_asset_id=source.id,
        target_asset_id=target.id,
        relationship_type=RelationshipType.CONNECTED_TO,
    )
    published.clear()

    await service.delete(relationship.id)
    assert await service.list_for_asset(source.id) == []
    assert any(event.event_name == "RelationshipDeleted" for event in published)

    neighbors = await topology_graph_client.get_neighbors(source.id)
    assert neighbors == []


__all__: list[str] = []
