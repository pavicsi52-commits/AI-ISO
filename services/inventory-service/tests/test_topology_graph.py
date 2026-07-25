"""Direct tests for :class:`TopologyGraphClient` against a real Neo4j instance."""

from __future__ import annotations

import uuid

from app.models.enums import RelationshipType
from app.topology.graph import TopologyGraphClient


async def test_upsert_and_delete_asset_node(topology_graph_client: TopologyGraphClient) -> None:
    asset_id = uuid.uuid4()
    org_id = uuid.uuid4()
    await topology_graph_client.upsert_asset_node(
        asset_id, organization_id=org_id, asset_type="virtual_machine", name="node-a"
    )
    # MERGE is idempotent -- upserting again must not raise or duplicate.
    await topology_graph_client.upsert_asset_node(
        asset_id, organization_id=org_id, asset_type="virtual_machine", name="node-a"
    )
    await topology_graph_client.delete_asset_node(asset_id)
    neighbors = await topology_graph_client.get_neighbors(asset_id)
    assert neighbors == []


async def test_upsert_relationship_and_neighbors(
    topology_graph_client: TopologyGraphClient,
) -> None:
    source_id, target_id = uuid.uuid4(), uuid.uuid4()
    org_id = uuid.uuid4()
    await topology_graph_client.upsert_asset_node(
        source_id, organization_id=org_id, asset_type="application", name="app"
    )
    await topology_graph_client.upsert_asset_node(
        target_id, organization_id=org_id, asset_type="database", name="db"
    )
    await topology_graph_client.upsert_relationship(
        source_id, target_id, RelationshipType.DEPENDS_ON
    )

    neighbors = await topology_graph_client.get_neighbors(source_id)
    assert len(neighbors) == 1
    assert neighbors[0]["id"] == str(target_id)
    assert neighbors[0]["relationship_type"] == "DEPENDS_ON"
    assert neighbors[0]["outgoing"] is True

    reverse_neighbors = await topology_graph_client.get_neighbors(target_id)
    assert reverse_neighbors[0]["outgoing"] is False


async def test_delete_relationship(topology_graph_client: TopologyGraphClient) -> None:
    source_id, target_id = uuid.uuid4(), uuid.uuid4()
    org_id = uuid.uuid4()
    await topology_graph_client.upsert_asset_node(
        source_id, organization_id=org_id, asset_type="application", name="app"
    )
    await topology_graph_client.upsert_asset_node(
        target_id, organization_id=org_id, asset_type="database", name="db"
    )
    await topology_graph_client.upsert_relationship(source_id, target_id, RelationshipType.RUNS_ON)
    await topology_graph_client.delete_relationship(source_id, target_id, RelationshipType.RUNS_ON)
    assert await topology_graph_client.get_neighbors(source_id) == []


async def test_dependency_graph_and_impact_analysis_multi_hop(
    topology_graph_client: TopologyGraphClient,
) -> None:
    web, db, storage = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    org_id = uuid.uuid4()
    for asset_id, name in ((web, "web"), (db, "db"), (storage, "storage")):
        await topology_graph_client.upsert_asset_node(
            asset_id, organization_id=org_id, asset_type="application", name=name
        )
    await topology_graph_client.upsert_relationship(web, db, RelationshipType.DEPENDS_ON)
    await topology_graph_client.upsert_relationship(db, storage, RelationshipType.RUNS_ON)

    dependencies = await topology_graph_client.get_dependency_graph(web, depth=2)
    dependency_ids = {n["id"]: n["distance"] for n in dependencies}
    assert dependency_ids == {str(db): 1, str(storage): 2}

    impact = await topology_graph_client.get_impact_analysis(storage, depth=2)
    impact_ids = {n["id"]: n["distance"] for n in impact}
    assert impact_ids == {str(db): 1, str(web): 2}


async def test_dependency_graph_depth_is_bounded(
    topology_graph_client: TopologyGraphClient,
) -> None:
    web, db = uuid.uuid4(), uuid.uuid4()
    org_id = uuid.uuid4()
    await topology_graph_client.upsert_asset_node(
        web, organization_id=org_id, asset_type="application", name="web"
    )
    await topology_graph_client.upsert_asset_node(
        db, organization_id=org_id, asset_type="database", name="db"
    )
    await topology_graph_client.upsert_relationship(web, db, RelationshipType.DEPENDS_ON)

    # depth=0 and depth=99 both get clamped into [1, 5] rather than
    # producing an empty/unbounded Cypher range.
    zero_depth = await topology_graph_client.get_dependency_graph(web, depth=0)
    assert len(zero_depth) == 1
    large_depth = await topology_graph_client.get_dependency_graph(web, depth=99)
    assert len(large_depth) == 1


__all__: list[str] = []
