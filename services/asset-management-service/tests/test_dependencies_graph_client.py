"""Direct tests for :class:`app.dependencies.graph_client.DependencyGraphClient`
against a real Neo4j graph.
"""

from __future__ import annotations

import uuid

from neo4j import AsyncDriver

from app.dependencies.graph_client import DependencyGraphClient
from tests.conftest import seed_dependency_graph


async def test_get_neighbors_returns_both_directions(real_neo4j_driver: AsyncDriver) -> None:
    center_id = uuid.uuid4()
    upstream_id = uuid.uuid4()
    downstream_id = uuid.uuid4()
    await seed_dependency_graph(
        real_neo4j_driver,
        [
            (center_id, "DEPENDS_ON", downstream_id),
            (upstream_id, "DEPENDS_ON", center_id),
        ],
    )
    client = DependencyGraphClient(real_neo4j_driver)

    neighbors = await client.get_neighbors(center_id)

    neighbor_ids = {record["id"] for record in neighbors}
    assert neighbor_ids == {str(upstream_id), str(downstream_id)}
