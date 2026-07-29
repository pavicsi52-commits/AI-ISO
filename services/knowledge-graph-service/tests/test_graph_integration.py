"""The graph layer against a real Neo4j.

A stub driver can confirm that this service *builds* the Cypher it
meant to. Only a real database can confirm that Neo4j accepts it, that
``MERGE`` is genuinely idempotent, and -- the one that matters most --
that a write submitted through a read transaction is refused. That last
guarantee is what ``POST /graph/cypher`` rests on, and it cannot be
asserted against a mock.

Isolation is by organization id rather than by transaction: Neo4j has no
SAVEPOINT, so each test works inside its own tenant and the fixture
purges it afterwards. That has a useful side effect -- every test is
also a tenant-isolation test.
"""

from __future__ import annotations

import contextlib
import json
import uuid

import pytest
from pydantic import ValidationError as PydanticValidationError
from shared_core.exceptions.dependency import DependencyError
from shared_core.exceptions.not_found import NotFoundError
from shared_core.exceptions.validation import ValidationError

from app.graph.client import GraphClient, QueryResult
from app.graph.entities import NodeInput, RelationshipInput
from app.graph.repository import GraphRepository
from app.graph.schema import GRAPH_NODE_LABEL, describe_schema, is_enterprise, node_labels
from app.models.enums import NodeType, RelationshipType, TraversalDirection


class TestSchema:
    """The constraints and indexes the graph actually has."""

    async def test_the_uniqueness_constraint_exists(self, graph_client: GraphClient) -> None:
        # This is the one that makes synchronization idempotent: MERGE on
        # (key, organization_id) finds or creates, so a re-run updates
        # instead of doubling the graph.
        described = await describe_schema(graph_client)
        assert "graph_node_key_unique" in described["constraints"]

    async def test_the_search_and_tenant_indexes_exist(self, graph_client: GraphClient) -> None:
        described = await describe_schema(graph_client)
        assert "graph_node_search" in described["indexes"]
        assert "graph_node_org_type" in described["indexes"]

    async def test_edition_is_reported_honestly(self, graph_client: GraphClient) -> None:
        # Property-existence constraints are Enterprise-only. The schema
        # module probes rather than attempting and failing, so this just
        # asserts the probe answers.
        assert isinstance(await is_enterprise(graph_client), bool)

    def test_every_node_carries_the_shared_label(self) -> None:
        # Two labels per node, so one constraint and one index set covers
        # everything while a type-scoped query still gets a scan.
        assert node_labels(NodeType.APPLICATION) == f"{GRAPH_NODE_LABEL}:Application"


class TestNodeWrites:
    """Creating, updating, and deleting nodes."""

    async def test_a_node_round_trips(
        self, graph: GraphRepository, organization_id: uuid.UUID
    ) -> None:
        written = await graph.upsert_node(
            organization_id,
            NodeInput(
                key="app-1",
                node_type=NodeType.APPLICATION,
                name="Billing",
                description="The billing application",
                properties={"tier": "gold"},
            ),
            source="test",
        )
        assert written.key == "app-1"
        assert written.node_type == "Application"

        read_back = await graph.get_node(organization_id, "app-1")
        assert read_back is not None
        assert read_back.name == "Billing"
        assert read_back.description == "The billing application"
        assert read_back.properties["tier"] == "gold"
        assert read_back.source == "test"
        assert read_back.created_at is not None

    async def test_merge_is_idempotent(
        self, graph: GraphRepository, organization_id: uuid.UUID
    ) -> None:
        # The property every sync depends on: writing the same key twice
        # updates rather than duplicating.
        for name in ("First", "Second"):
            await graph.upsert_node(
                organization_id,
                NodeInput(key="app-1", node_type=NodeType.APPLICATION, name=name),
            )
        assert await graph.count_nodes(organization_id) == 1
        node = await graph.get_node(organization_id, "app-1")
        assert node is not None
        assert node.name == "Second"

    async def test_created_at_survives_an_update(
        self, graph: GraphRepository, organization_id: uuid.UUID
    ) -> None:
        # ON CREATE SET, not SET -- otherwise every sync would reset the
        # age of every node it touched.
        first = await graph.upsert_node(
            organization_id,
            NodeInput(key="app-1", node_type=NodeType.APPLICATION, name="First"),
        )
        second = await graph.upsert_node(
            organization_id,
            NodeInput(key="app-1", node_type=NodeType.APPLICATION, name="Second"),
        )
        assert first.created_at == second.created_at

    async def test_bulk_writes_group_by_label(
        self, graph: GraphRepository, organization_id: uuid.UUID
    ) -> None:
        written = await graph.upsert_nodes(
            organization_id,
            [
                NodeInput(key=f"vm-{i}", node_type=NodeType.VIRTUAL_MACHINE, name=f"vm-{i}")
                for i in range(5)
            ]
            + [NodeInput(key="db-1", node_type=NodeType.DATABASE, name="db")],
        )
        assert written == 6
        assert await graph.count_nodes(organization_id) == 6

    async def test_bulk_write_of_nothing_is_a_no_op(
        self, graph: GraphRepository, organization_id: uuid.UUID
    ) -> None:
        assert await graph.upsert_nodes(organization_id, []) == 0

    async def test_a_reserved_property_name_is_refused(self) -> None:
        # A payload setting organization_id would move the node into
        # another tenant's graph.
        with pytest.raises(ValidationError, match="managed by the graph"):
            NodeInput(
                key="app-1",
                node_type=NodeType.APPLICATION,
                name="Billing",
                properties={"organization_id": "someone-else"},
            )

    async def test_deleting_a_node_takes_its_relationships(
        self, seeded_graph: GraphRepository, organization_id: uuid.UUID
    ) -> None:
        before = await seeded_graph.count_relationships(organization_id)
        assert await seeded_graph.delete_node(organization_id, "vm-1") is True
        after = await seeded_graph.count_relationships(organization_id)
        assert after < before, "DETACH DELETE, or the graph keeps dangling edges"

    async def test_deleting_an_absent_node_reports_it(
        self, graph: GraphRepository, organization_id: uuid.UUID
    ) -> None:
        assert await graph.delete_node(organization_id, "ghost") is False

    async def test_requiring_an_absent_node_raises(
        self, graph: GraphRepository, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError, match="No graph node with key"):
            await graph.require_node(organization_id, "ghost")


class TestTenantIsolation:
    """One organization never sees another's graph."""

    async def test_another_organization_sees_nothing(
        self, seeded_graph: GraphRepository, organization_id: uuid.UUID
    ) -> None:
        other = uuid.uuid4()
        assert await seeded_graph.count_nodes(other) == 0
        assert await seeded_graph.get_node(other, "app-1") is None
        assert await seeded_graph.list_nodes(other) == []

    async def test_the_same_key_in_two_organizations_is_two_nodes(
        self, graph: GraphRepository, organization_id: uuid.UUID
    ) -> None:
        # The uniqueness constraint is on (key, organization_id), not key
        # alone -- otherwise two tenants could not both have "host-1".
        other = uuid.uuid4()
        try:
            await graph.upsert_node(
                organization_id,
                NodeInput(key="shared", node_type=NodeType.APPLICATION, name="Mine"),
            )
            await graph.upsert_node(
                other, NodeInput(key="shared", node_type=NodeType.APPLICATION, name="Theirs")
            )
            mine = await graph.get_node(organization_id, "shared")
            theirs = await graph.get_node(other, "shared")
            assert mine is not None and theirs is not None
            assert mine.name == "Mine"
            assert theirs.name == "Theirs"
        finally:
            await graph.purge_organization(other)

    async def test_a_traversal_cannot_cross_tenants(
        self, seeded_graph: GraphRepository, organization_id: uuid.UUID
    ) -> None:
        other = uuid.uuid4()
        try:
            await seeded_graph.upsert_node(
                other, NodeInput(key="app-1", node_type=NodeType.APPLICATION, name="Theirs")
            )
            result = await seeded_graph.traverse(other, "app-1", depth=3)
            # Their own app-1 and nothing else. The seeded organization
            # has a node under the same key with four neighbours; not one
            # of them may appear here.
            assert result.node_keys() == {"app-1"}, "a foreign graph must not be reachable"
            assert result.relationships == []
        finally:
            await seeded_graph.purge_organization(other)


class TestRelationships:
    """Edges between nodes."""

    async def test_a_relationship_round_trips(
        self, seeded_graph: GraphRepository, organization_id: uuid.UUID
    ) -> None:
        edges = await seeded_graph.list_relationships(organization_id, node_key="app-1")
        assert {edge.relationship_type for edge in edges} == {"RUNS_ON", "DEPENDS_ON"}

    async def test_an_edge_needs_both_endpoints(
        self, graph: GraphRepository, organization_id: uuid.UUID
    ) -> None:
        # An edge is created between nodes, never conjuring them -- a
        # write that could invent endpoints would paper over its own
        # ordering bugs with half-populated nodes.
        await graph.upsert_node(
            organization_id, NodeInput(key="a", node_type=NodeType.APPLICATION, name="a")
        )
        with pytest.raises(NotFoundError, match="do not exist"):
            await graph.upsert_relationship(
                organization_id,
                RelationshipInput(
                    from_key="a", to_key="ghost", relationship_type=RelationshipType.USES
                ),
            )

    async def test_a_self_loop_is_refused_at_construction(self) -> None:
        # Enforced on the model rather than in a separate validator, so
        # the importer and the sync mappers -- which build these
        # directly -- get one rejected row instead of an aborted batch.
        # A self-loop makes every dependency traversal cyclic and every
        # blast radius infinite.
        with pytest.raises(PydanticValidationError, match="cannot relate to itself"):
            RelationshipInput(
                from_key="a", to_key="a", relationship_type=RelationshipType.DEPENDS_ON
            )

    async def test_relationship_merge_is_idempotent(
        self, seeded_graph: GraphRepository, organization_id: uuid.UUID
    ) -> None:
        before = await seeded_graph.count_relationships(organization_id)
        await seeded_graph.upsert_relationship(
            organization_id,
            RelationshipInput(
                from_key="app-1", to_key="vm-1", relationship_type=RelationshipType.RUNS_ON
            ),
        )
        assert await seeded_graph.count_relationships(organization_id) == before

    async def test_weight_is_stored_and_read_back(
        self, seeded_graph: GraphRepository, organization_id: uuid.UUID
    ) -> None:
        await seeded_graph.upsert_relationship(
            organization_id,
            RelationshipInput(
                from_key="app-1",
                to_key="db-1",
                relationship_type=RelationshipType.DEPENDS_ON,
                weight=0.25,
            ),
        )
        edges = await seeded_graph.list_relationships(organization_id, node_key="app-1")
        depends = next(e for e in edges if e.relationship_type == "DEPENDS_ON")
        assert depends.weight == pytest.approx(0.25)

    async def test_deleting_a_relationship(
        self, seeded_graph: GraphRepository, organization_id: uuid.UUID
    ) -> None:
        assert (
            await seeded_graph.delete_relationship(
                organization_id,
                from_key="app-1",
                to_key="db-1",
                relationship_type=RelationshipType.DEPENDS_ON,
            )
            is True
        )
        assert (
            await seeded_graph.delete_relationship(
                organization_id,
                from_key="app-1",
                to_key="db-1",
                relationship_type=RelationshipType.DEPENDS_ON,
            )
            is False
        )

    async def test_a_derived_relationship_key_is_stable(
        self, seeded_graph: GraphRepository, organization_id: uuid.UUID
    ) -> None:
        # Derived from endpoints and type rather than stored, because
        # Neo4j relationship ids are internal and unstable across a
        # restore.
        edges = await seeded_graph.list_relationships(organization_id, node_key="app-1")
        for edge in edges:
            assert edge.relationship_key == (
                f"{edge.from_key}|{edge.relationship_type}|{edge.to_key}"
            )


class TestTraversal:
    """Walking the graph, and which way."""

    async def test_outgoing_answers_what_do_i_need(
        self, seeded_graph: GraphRepository, organization_id: uuid.UUID
    ) -> None:
        result = await seeded_graph.traverse(
            organization_id, "app-1", direction=TraversalDirection.OUTGOING, depth=3
        )
        # The root is part of its own topology. Omitting it would leave
        # every edge out of app-1 pointing at a node the subgraph does
        # not contain -- unrenderable, and dropped outright by
        # Graph.from_subgraph before any analysis ran.
        assert result.node_keys() == {"app-1", "vm-1", "db-1", "host-1", "vm-2"}

    async def test_incoming_answers_who_breaks_if_i_go_down(
        self, seeded_graph: GraphRepository, organization_id: uuid.UUID
    ) -> None:
        # The distinction that matters most: getting it backwards gives a
        # confident wrong answer during an incident.
        result = await seeded_graph.traverse(
            organization_id, "host-1", direction=TraversalDirection.INCOMING, depth=3
        )
        assert result.node_keys() == {"host-1", "vm-1", "vm-2", "app-1", "db-1"}

    async def test_depth_bounds_the_walk(
        self, seeded_graph: GraphRepository, organization_id: uuid.UUID
    ) -> None:
        shallow = await seeded_graph.traverse(
            organization_id, "app-1", direction=TraversalDirection.OUTGOING, depth=1
        )
        assert shallow.node_keys() == {"app-1", "vm-1", "db-1"}

    async def test_relationship_types_filter_the_walk(
        self, seeded_graph: GraphRepository, organization_id: uuid.UUID
    ) -> None:
        result = await seeded_graph.traverse(
            organization_id,
            "app-1",
            direction=TraversalDirection.OUTGOING,
            relationship_types=[RelationshipType.DEPENDS_ON],
            depth=3,
        )
        assert result.node_keys() == {"app-1", "db-1"}

    async def test_node_types_filter_the_result(
        self, seeded_graph: GraphRepository, organization_id: uuid.UUID
    ) -> None:
        result = await seeded_graph.traverse(
            organization_id,
            "app-1",
            direction=TraversalDirection.OUTGOING,
            node_types=[NodeType.PHYSICAL_SERVER],
            depth=3,
        )
        # The node-type filter narrows what the walk *reaches*; it never
        # removes the node the caller asked about.
        assert result.node_keys() == {"app-1", "host-1"}

    async def test_nodes_are_de_duplicated(
        self, seeded_graph: GraphRepository, organization_id: uuid.UUID
    ) -> None:
        # host-1 is reachable by two routes; Neo4j returns one row per
        # path, so without de-duplication it would appear twice.
        result = await seeded_graph.traverse(
            organization_id, "app-1", direction=TraversalDirection.OUTGOING, depth=3
        )
        keys = [n.key for n in result.nodes]
        assert len(keys) == len(set(keys))

    async def test_an_isolated_node_returns_itself_not_nothing(
        self, graph: GraphRepository, organization_id: uuid.UUID
    ) -> None:
        # "This node has no neighbours" and "there is no such node" are
        # different answers, and a caller has to be able to tell them
        # apart. OPTIONAL MATCH is what keeps them distinguishable.
        await graph.upsert_node(
            organization_id,
            NodeInput(key="island", node_type=NodeType.APPLICATION, name="island"),
        )
        result = await graph.traverse(organization_id, "island", depth=3)
        assert result.node_keys() == {"island"}
        assert result.relationships == []

    async def test_every_edge_endpoint_is_present_in_the_node_set(
        self, seeded_graph: GraphRepository, organization_id: uuid.UUID
    ) -> None:
        # The invariant behind including the root. Graph.from_subgraph
        # drops edges pointing outside the node set, so a subgraph that
        # breaks this does not fail loudly -- it quietly analyses a
        # different graph from the one it returned.
        result = await seeded_graph.traverse(organization_id, "app-1", depth=3)
        keys = result.node_keys()
        endpoints = {one.from_key for one in result.relationships} | {
            one.to_key for one in result.relationships
        }
        assert endpoints <= keys

    async def test_a_traversal_carries_no_driver_native_values(
        self, seeded_graph: GraphRepository, organization_id: uuid.UUID
    ) -> None:
        # The driver's DateTime is not JSON serialisable, and an unpopped
        # one survives every dict-shaped assertion to fail only at
        # encode time -- which is to say, in the response, not the test.
        result = await seeded_graph.traverse(organization_id, "app-1", depth=3)
        assert json.dumps(result.as_dict())

    async def test_an_out_of_range_depth_is_refused(
        self, seeded_graph: GraphRepository, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(ValidationError, match="between 1 and"):
            await seeded_graph.traverse(organization_id, "app-1", depth=99)

    async def test_neighbours_are_only_one_hop(
        self, seeded_graph: GraphRepository, organization_id: uuid.UUID
    ) -> None:
        found = await seeded_graph.neighbours(
            organization_id, "app-1", direction=TraversalDirection.OUTGOING
        )
        assert {n.key for n in found} == {"vm-1", "db-1"}

    async def test_shortest_path_finds_the_shorter_of_two_routes(
        self, seeded_graph: GraphRepository, organization_id: uuid.UUID
    ) -> None:
        # app-1 -> vm-1 -> host-1 is two hops;
        # app-1 -> db-1 -> vm-2 -> host-1 is three.
        path = await seeded_graph.shortest_path(organization_id, from_key="app-1", to_key="host-1")
        assert [n.key for n in path.nodes] == ["app-1", "vm-1", "host-1"]

    async def test_no_path_returns_an_empty_subgraph(
        self, seeded_graph: GraphRepository, organization_id: uuid.UUID
    ) -> None:
        # A real answer -- "these are not connected" -- not a failure.
        await seeded_graph.upsert_node(
            organization_id,
            NodeInput(key="island", node_type=NodeType.SENSOR, name="island"),
        )
        path = await seeded_graph.shortest_path(organization_id, from_key="app-1", to_key="island")
        assert path.nodes == []


class TestAggregates:
    """Counts computed in the database, not in Python."""

    async def test_degrees_are_counted_in_cypher(
        self, seeded_graph: GraphRepository, organization_id: uuid.UUID
    ) -> None:
        degrees = await seeded_graph.degrees(organization_id)
        assert degrees["app-1"] == 2
        assert degrees["host-1"] == 2

    async def test_type_counts(
        self, seeded_graph: GraphRepository, organization_id: uuid.UUID
    ) -> None:
        counts = await seeded_graph.type_counts(organization_id)
        assert counts["VirtualMachine"] == 2
        assert counts["Application"] == 1

    async def test_relationship_type_counts(
        self, seeded_graph: GraphRepository, organization_id: uuid.UUID
    ) -> None:
        counts = await seeded_graph.relationship_type_counts(organization_id)
        assert counts["RUNS_ON"] == 4
        assert counts["DEPENDS_ON"] == 1

    async def test_orphans_are_found(
        self, seeded_graph: GraphRepository, organization_id: uuid.UUID
    ) -> None:
        # Almost always a synchronization bug rather than a fact about
        # the estate, which is why it gets its own figure.
        await seeded_graph.upsert_node(
            organization_id,
            NodeInput(key="unattached", node_type=NodeType.SENSOR, name="unattached"),
        )
        assert await seeded_graph.orphan_keys(organization_id) == ["unattached"]

    async def test_listing_filters_and_paginates(
        self, seeded_graph: GraphRepository, organization_id: uuid.UUID
    ) -> None:
        vms = await seeded_graph.list_nodes(organization_id, node_types=[NodeType.VIRTUAL_MACHINE])
        assert {n.key for n in vms} == {"vm-1", "vm-2"}

        page = await seeded_graph.list_nodes(organization_id, limit=2, offset=0)
        assert len(page) == 2

    async def test_listing_filters_by_source(
        self, seeded_graph: GraphRepository, organization_id: uuid.UUID
    ) -> None:
        assert len(await seeded_graph.list_nodes(organization_id, source="test")) == 5
        assert await seeded_graph.list_nodes(organization_id, source="other") == []


class TestReadOnlyEnforcement:
    """The guarantee POST /graph/cypher rests on."""

    async def test_neo4j_refuses_a_write_in_a_read_transaction(
        self, graph_client: GraphClient, organization_id: uuid.UUID
    ) -> None:
        # This is the layer that actually holds. app.cypher.guard makes
        # the refusal legible; the database makes it true. If the guard
        # ever misses something, this is what stops it mattering.
        with pytest.raises(DependencyError, match="Graph query failed"):
            await graph_client.read(
                "CREATE (n:GraphNode {key: 'sneaky', organization_id: $org}) RETURN n",
                {"org": str(organization_id)},
            )

    async def test_the_write_did_not_happen(
        self, graph: GraphRepository, graph_client: GraphClient, organization_id: uuid.UUID
    ) -> None:
        # Suppressed rather than asserted: this test is about the state
        # of the database afterwards, not about which error came back --
        # a refusal that still wrote the node would be the real failure.
        with contextlib.suppress(DependencyError):
            await graph_client.read(
                "CREATE (n:GraphNode {key: 'sneaky', organization_id: $org}) RETURN n",
                {"org": str(organization_id)},
            )
        assert await graph.get_node(organization_id, "sneaky") is None

    async def test_a_read_still_works(
        self, seeded_graph: GraphRepository, graph_client: GraphClient, organization_id: uuid.UUID
    ) -> None:
        result = await graph_client.read(
            f"MATCH (n:{GRAPH_NODE_LABEL} {{organization_id: $org}}) RETURN count(n) AS total",
            {"org": str(organization_id)},
        )
        assert result.scalar("total") == 5


class TestClientBehaviour:
    """Result bounding and failure reporting."""

    async def test_results_are_bounded_and_flagged(
        self, seeded_graph: GraphRepository, graph_client: GraphClient, organization_id: uuid.UUID
    ) -> None:
        # A partial answer that says so beats an unbounded one that
        # exhausts the process.
        result = await graph_client.read(
            f"MATCH (n:{GRAPH_NODE_LABEL} {{organization_id: $org}}) RETURN n.key AS key",
            {"org": str(organization_id)},
            max_records=2,
        )
        assert result.row_count == 2
        assert result.truncated is True

    async def test_a_bad_statement_becomes_a_dependency_error(
        self, graph_client: GraphClient
    ) -> None:
        with pytest.raises(DependencyError, match="Graph query failed"):
            await graph_client.read("THIS IS NOT CYPHER")

    async def test_an_unconfigured_client_says_so(self) -> None:
        client = GraphClient(None, enabled=False)
        assert client.enabled is False
        with pytest.raises(DependencyError, match="not configured"):
            await client.read("MATCH (n) RETURN n")

    async def test_verify_reports_reachability(self, graph_client: GraphClient) -> None:
        assert await graph_client.verify() is True
        assert await GraphClient(None, enabled=False).verify() is False

    async def test_a_batched_write_is_all_or_nothing(
        self, graph: GraphRepository, graph_client: GraphClient, organization_id: uuid.UUID
    ) -> None:
        # A bulk import that fails halfway must not leave the graph
        # holding half a payload.
        with pytest.raises(DependencyError):
            await graph_client.write_many(
                [
                    (
                        f"CREATE (n:{GRAPH_NODE_LABEL} {{key: 'batch-1', organization_id: $org}})",
                        {"org": str(organization_id)},
                    ),
                    ("THIS IS NOT CYPHER", {}),
                ]
            )
        assert await graph.get_node(organization_id, "batch-1") is None

    async def test_an_empty_batch_is_a_no_op(self, graph_client: GraphClient) -> None:
        assert await graph_client.write_many([]) == 0

    async def test_a_query_result_scalar_defaults(self) -> None:
        empty = QueryResult()
        assert empty.scalar("missing", "fallback") == "fallback"
        assert empty.row_count == 0
