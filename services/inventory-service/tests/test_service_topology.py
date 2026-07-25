"""Tests for :class:`TopologyService`, including its Postgres cache layer."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import RelationshipType
from app.repositories.asset_topology_cache import AssetTopologyCacheRepository
from app.services.topology import TopologyService
from app.topology.graph import TopologyGraphClient
from tests.conftest import make_asset


def _service(db_session: AsyncSession, graph: TopologyGraphClient) -> TopologyService:
    return TopologyService(graph, AssetTopologyCacheRepository(db_session))


async def test_sync_and_get_neighbors_uses_cache_on_second_call(
    db_session: AsyncSession, topology_graph_client: TopologyGraphClient
) -> None:
    service = _service(db_session, topology_graph_client)
    source = await make_asset(db_session, name="source")
    target = await make_asset(db_session, name="target", organization_id=source.organization_id)

    await service.sync_asset_node(
        source.id,
        organization_id=source.organization_id,
        asset_type=str(source.asset_type),
        name=source.name,
    )
    await service.sync_asset_node(
        target.id,
        organization_id=target.organization_id,
        asset_type=str(target.asset_type),
        name=target.name,
    )
    await service.sync_relationship(source.id, target.id, RelationshipType.DEPENDS_ON)

    first = await service.get_neighbors(source.id, organization_id=source.organization_id)
    assert len(first) == 1

    # Remove the edge directly in Neo4j -- if the second call still returns
    # one neighbor, it proves the Postgres cache (not a fresh Neo4j round
    # trip) served the second call.
    await topology_graph_client.delete_relationship(
        source.id, target.id, RelationshipType.DEPENDS_ON
    )
    second = await service.get_neighbors(source.id, organization_id=source.organization_id)
    assert len(second) == 1


async def test_get_dependency_graph_and_impact_analysis(
    db_session: AsyncSession, topology_graph_client: TopologyGraphClient
) -> None:
    service = _service(db_session, topology_graph_client)
    source = await make_asset(db_session, name="source")
    target = await make_asset(db_session, name="target", organization_id=source.organization_id)
    await service.sync_asset_node(
        source.id,
        organization_id=source.organization_id,
        asset_type=str(source.asset_type),
        name=source.name,
    )
    await service.sync_asset_node(
        target.id,
        organization_id=target.organization_id,
        asset_type=str(target.asset_type),
        name=target.name,
    )
    await service.sync_relationship(source.id, target.id, RelationshipType.DEPENDS_ON)

    dependencies = await service.get_dependency_graph(
        source.id, organization_id=source.organization_id
    )
    assert [n["id"] for n in dependencies] == [str(target.id)]

    impact = await service.get_impact_analysis(target.id, organization_id=target.organization_id)
    assert [n["id"] for n in impact] == [str(source.id)]


async def test_remove_asset_node_and_relationship(
    db_session: AsyncSession, topology_graph_client: TopologyGraphClient
) -> None:
    service = _service(db_session, topology_graph_client)
    source = await make_asset(db_session, name="source")
    target = await make_asset(db_session, name="target", organization_id=source.organization_id)
    await service.sync_asset_node(
        source.id,
        organization_id=source.organization_id,
        asset_type=str(source.asset_type),
        name=source.name,
    )
    await service.sync_asset_node(
        target.id,
        organization_id=target.organization_id,
        asset_type=str(target.asset_type),
        name=target.name,
    )
    await service.sync_relationship(source.id, target.id, RelationshipType.RUNS_ON)
    await service.remove_relationship(source.id, target.id, RelationshipType.RUNS_ON)
    await service.remove_asset_node(source.id)
    await service.remove_asset_node(target.id)


__all__: list[str] = []
