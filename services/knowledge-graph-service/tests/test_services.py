"""The service layer, against real PostgreSQL and real Neo4j.

These tests sit above :mod:`tests.test_graph_integration`: that file
proves the Cypher is right, this one proves the *bookkeeping* around it
is. A graph write that succeeds but records no change history, or
announces no event, has lost the thing that makes "why is this node
different from yesterday?" answerable -- and no amount of correct Cypher
recovers it.

Both stores are real and both are isolated: PostgreSQL by SAVEPOINT,
Neo4j by a per-test organization id. That means a test can assert a
Postgres row and a Neo4j node were written by the same call and have
both statements mean something.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from shared_core.database.session import session_scope
from shared_core.enums.health_status import HealthStatus
from shared_core.enums.severity import Severity
from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError
from shared_core.exceptions.validation import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.dependencies.engine import DependencyEngine
from app.graph.entities import NodeInput, RelationshipInput
from app.graph.repository import GraphRepository
from app.models.enums import (
    AnalyticsAlgorithm,
    AuditAction,
    AuditOutcome,
    ChangeAction,
    LifecycleState,
    NodeType,
    QueryKind,
    RelationshipType,
    TraversalDirection,
    TwinType,
)
from app.repositories.graph_audit import GraphAuditRepository
from app.repositories.graph_metadata import GraphMetadataRepository
from app.repositories.graph_query import GraphQueryRepository
from app.repositories.graph_report import GraphReportRepository
from app.repositories.graph_saved_query import GraphSavedQueryRepository
from app.repositories.graph_statistics import GraphStatisticsRepository
from app.repositories.graph_sync_job import GraphSyncJobRepository
from app.services.analytics import AnalyticsService
from app.services.audit import AuditService, action_of, outcome_of
from app.services.graph import GraphService
from app.services.query import BUILTIN_QUERIES, QueryService
from app.services.statistics import StatisticsService
from tests.conftest import RecordingPublisher

pytestmark = pytest.mark.asyncio


class TestGraphServiceNodes:
    """Node writes and the record they leave behind."""

    async def test_creating_a_node_writes_it_and_records_the_change(
        self,
        graph_service: GraphService,
        db_session: AsyncSession,
        organization_id: uuid.UUID,
        publisher: RecordingPublisher,
    ) -> None:
        stored = await graph_service.create_node(
            organization_id,
            NodeInput(key="app-1", node_type=NodeType.APPLICATION, name="Billing"),
        )
        assert stored.key == "app-1"

        # The graph write and the Postgres row are the same call's work;
        # asserting only the first would let a silent history failure
        # through.
        await db_session.flush()
        history = await graph_service.history(organization_id)
        assert [str(one.action) for one in history] == [str(ChangeAction.NODE_CREATED)]
        assert publisher.names == ["GraphNodeCreated"]

    async def test_a_second_write_is_an_update_not_a_creation(
        self,
        graph_service: GraphService,
        organization_id: uuid.UUID,
        publisher: RecordingPublisher,
    ) -> None:
        # A subscriber reacting to "a new node appeared" must not fire
        # every time a property changes, so the distinction is carried
        # in the event name rather than left to the subscriber.
        for name in ("First", "Second"):
            await graph_service.create_node(
                organization_id,
                NodeInput(key="app-1", node_type=NodeType.APPLICATION, name=name),
            )
        assert publisher.names == ["GraphNodeCreated", "GraphNodeUpdated"]

    async def test_the_change_log_records_which_it_was(
        self, graph_service: GraphService, organization_id: uuid.UUID
    ) -> None:
        for name in ("First", "Second"):
            await graph_service.create_node(
                organization_id,
                NodeInput(key="app-1", node_type=NodeType.APPLICATION, name=name),
            )
        actions = [str(one.action) for one in await graph_service.history(organization_id)]
        assert set(actions) == {str(ChangeAction.NODE_CREATED), str(ChangeAction.NODE_UPDATED)}

    async def test_getting_an_absent_node_raises(
        self, graph_service: GraphService, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await graph_service.get_node(organization_id, "ghost")

    async def test_deleting_a_node_records_what_it_was(
        self, graph_service: GraphService, organization_id: uuid.UUID
    ) -> None:
        # The `before` payload is the whole point of a delete entry: after
        # the fact the graph cannot tell you what was removed.
        await graph_service.create_node(
            organization_id,
            NodeInput(key="app-1", node_type=NodeType.APPLICATION, name="Billing"),
        )
        assert await graph_service.delete_node(organization_id, "app-1") is True

        entries = await graph_service.history(organization_id, node_key="app-1")
        deleted = [one for one in entries if str(one.action) == str(ChangeAction.NODE_DELETED)]
        assert len(deleted) == 1
        assert deleted[0].before == {"name": "Billing", "node_type": "Application"}

    async def test_deleting_an_absent_node_reports_it_without_a_change_entry(
        self, graph_service: GraphService, organization_id: uuid.UUID
    ) -> None:
        assert await graph_service.delete_node(organization_id, "ghost") is False
        assert await graph_service.history(organization_id) == []

    async def test_deleting_a_node_takes_its_metadata(
        self,
        graph_service: GraphService,
        twin_service: Any,
        db_session: AsyncSession,
        organization_id: uuid.UUID,
    ) -> None:
        # A metadata row left behind is unreachable by every read path --
        # they all join on the node key -- while still holding the
        # unique constraint that stops the node being recreated cleanly.
        await graph_service.create_node(
            organization_id,
            NodeInput(key="app-1", node_type=NodeType.APPLICATION, name="Billing"),
        )
        await twin_service.set_state(organization_id, "app-1", criticality=0.9)
        assert await twin_service.list_twins(organization_id) != []

        await graph_service.delete_node(organization_id, "app-1")
        await db_session.flush()
        assert await twin_service.list_twins(organization_id) == []

    async def test_listing_filters_by_type(
        self, graph_service: GraphService, organization_id: uuid.UUID
    ) -> None:
        for key, node_type in (("app-1", NodeType.APPLICATION), ("vm-1", NodeType.VIRTUAL_MACHINE)):
            await graph_service.create_node(
                organization_id, NodeInput(key=key, node_type=node_type, name=key)
            )
        found = await graph_service.list_nodes(organization_id, node_types=[NodeType.APPLICATION])
        assert [one.key for one in found] == ["app-1"]


class TestGraphServiceRelationships:
    """Relationship writes and their record."""

    async def test_creating_a_relationship_records_and_announces_it(
        self,
        graph_service: GraphService,
        organization_id: uuid.UUID,
        publisher: RecordingPublisher,
    ) -> None:
        for key in ("app-1", "vm-1"):
            await graph_service.create_node(
                organization_id, NodeInput(key=key, node_type=NodeType.APPLICATION, name=key)
            )
        publisher.events.clear()

        stored = await graph_service.create_relationship(
            organization_id,
            RelationshipInput(
                from_key="app-1", to_key="vm-1", relationship_type=RelationshipType.RUNS_ON
            ),
        )
        assert stored.relationship_key == "app-1|RUNS_ON|vm-1"
        assert publisher.names == ["GraphRelationshipCreated"]

    async def test_a_relationship_to_a_missing_node_is_refused(
        self, graph_service: GraphService, organization_id: uuid.UUID
    ) -> None:
        # MERGE would happily create the endpoint, which is how a typo
        # becomes a permanent phantom node.
        await graph_service.create_node(
            organization_id, NodeInput(key="app-1", node_type=NodeType.APPLICATION, name="a")
        )
        with pytest.raises(NotFoundError):
            await graph_service.create_relationship(
                organization_id,
                RelationshipInput(
                    from_key="app-1", to_key="ghost", relationship_type=RelationshipType.RUNS_ON
                ),
            )

    async def test_deleting_a_relationship_records_and_announces_it(
        self,
        graph_service: GraphService,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
        publisher: RecordingPublisher,
    ) -> None:
        del seeded_graph
        publisher.events.clear()
        removed = await graph_service.delete_relationship(
            organization_id,
            from_key="app-1",
            to_key="vm-1",
            relationship_type=RelationshipType.RUNS_ON,
        )
        assert removed is True
        assert publisher.names == ["GraphRelationshipRemoved"]

    async def test_deleting_an_absent_relationship_announces_nothing(
        self,
        graph_service: GraphService,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
        publisher: RecordingPublisher,
    ) -> None:
        del seeded_graph
        publisher.events.clear()
        removed = await graph_service.delete_relationship(
            organization_id,
            from_key="app-1",
            to_key="host-1",
            relationship_type=RelationshipType.RUNS_ON,
        )
        assert removed is False
        assert publisher.events == []

    async def test_listing_relationships_around_one_node(
        self,
        graph_service: GraphService,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        found = await graph_service.list_relationships(
            organization_id, node_key="app-1", direction=TraversalDirection.OUTGOING
        )
        assert {one.to_key for one in found} == {"vm-1", "db-1"}


class TestGraphServiceTraversal:
    """Topology, neighbours, and paths through the service layer."""

    async def test_topology_returns_the_surrounding_subgraph(
        self,
        graph_service: GraphService,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        subgraph = await graph_service.topology(organization_id, "app-1", depth=2)
        assert {one.key for one in subgraph.nodes} >= {"app-1", "vm-1", "db-1"}

    async def test_topology_of_a_missing_root_raises(
        self,
        graph_service: GraphService,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        # Checked explicitly rather than returning an empty subgraph: a
        # caller asking about a node that does not exist has a different
        # problem from one asking about an isolated node.
        del seeded_graph
        with pytest.raises(NotFoundError):
            await graph_service.topology(organization_id, "ghost")

    async def test_neighbours_are_only_the_directly_adjacent(
        self,
        graph_service: GraphService,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        found = await graph_service.neighbours(
            organization_id, "app-1", direction=TraversalDirection.OUTGOING
        )
        # host-1 is two hops away and must not appear.
        assert {one.key for one in found} == {"vm-1", "db-1"}

    async def test_the_shortest_path_takes_the_shorter_branch(
        self,
        graph_service: GraphService,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        # Two routes reach host-1: via vm-1 (2 hops) and via db-1/vm-2
        # (3 hops). This is why the fixture branches.
        path = await graph_service.shortest_path(organization_id, from_key="app-1", to_key="host-1")
        assert {one.key for one in path.nodes} == {"app-1", "vm-1", "host-1"}

    async def test_no_path_is_an_answer_not_a_failure(
        self,
        graph_service: GraphService,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        await seeded_graph.upsert_node(
            organization_id,
            NodeInput(key="island", node_type=NodeType.APPLICATION, name="island"),
        )
        path = await graph_service.shortest_path(organization_id, from_key="app-1", to_key="island")
        assert path.nodes == []

    async def test_counts_report_both_totals_and_breakdowns(
        self,
        graph_service: GraphService,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        counts = await graph_service.counts(organization_id)
        assert counts["node_count"] == 5
        assert counts["relationship_count"] == 5
        assert counts["node_type_counts"]["VirtualMachine"] == 2
        assert counts["relationship_type_counts"]["RUNS_ON"] == 4


class TestAuditService:
    """The trail, including the entries that matter most."""

    async def test_an_entry_round_trips(
        self, audit_service: AuditService, organization_id: uuid.UUID
    ) -> None:
        stored = await audit_service.record(
            organization_id=organization_id,
            action=AuditAction.NODE_CHANGED,
            entity_type="Application",
            entity_key="app-1",
        )
        assert stored is not None
        entries = await audit_service.list_for_org(organization_id)
        assert [one.entity_key for one in entries] == ["app-1"]

    async def test_a_refusal_is_recorded_as_denied(
        self, audit_service: AuditService, organization_id: uuid.UUID
    ) -> None:
        # The entry this trail exists for. A probe at POST /graph/cypher
        # changes no state, so a trail of successes alone would show
        # nothing at all where the interesting event was.
        await audit_service.record_denied(
            organization_id=organization_id,
            action=AuditAction.CYPHER_EXECUTED,
            entity_type="Cypher",
            reason="DETACH DELETE is a write clause",
        )
        entries = await audit_service.list_for_org(organization_id)
        assert outcome_of(entries[0]) is AuditOutcome.DENIED
        assert "DETACH DELETE" in (entries[0].reason or "")

    async def test_a_denied_entry_survives_the_rollback_of_the_request_that_raised(
        self,
        db_session: AsyncSession,
        db_session_factory: async_sessionmaker[AsyncSession],
        organization_id: uuid.UUID,
    ) -> None:
        # The shape of the real thing: the route records a refusal and
        # then *raises* the refusal, and `session_scope` rolls the
        # request's transaction back on the way out. An entry written on
        # that shared session goes with it -- so the trail whose entire
        # purpose is recording a probe at POST /graph/cypher recorded
        # nothing at all. A request-scoped SAVEPOINT never rolls back the
        # way a real request does, which is why the API test passed and
        # only a live container disagreed.
        service = AuditService(GraphAuditRepository(db_session), session_factory=db_session_factory)
        with pytest.raises(ValidationError):
            async with session_scope(db_session_factory):
                await service.record_denied(
                    organization_id=organization_id,
                    action=AuditAction.CYPHER_EXECUTED,
                    entity_type="cypher",
                    reason="DETACH DELETE is a write clause",
                )
                raise ValidationError("refused")

        async with db_session_factory() as reader:
            entries = await GraphAuditRepository(reader).list_for_org(organization_id)
        assert [outcome_of(one) for one in entries] == [AuditOutcome.DENIED]

    async def test_a_storage_failure_does_not_fail_the_audited_action(
        self, audit_service: AuditService, organization_id: uuid.UUID
    ) -> None:
        # Deliberate: refusing a topology query because an audit insert
        # deadlocked turns a bookkeeping problem into an operational one
        # during an incident. Forced by an entity_type far over the
        # column width, so a genuine database error is what gets
        # swallowed rather than a simulated one.
        stored = await audit_service.record(
            organization_id=organization_id,
            action=AuditAction.NODE_CHANGED,
            entity_type="x" * 5_000,
        )
        assert stored is None

    async def test_filtering_by_action(
        self, audit_service: AuditService, organization_id: uuid.UUID
    ) -> None:
        for action in (AuditAction.NODE_CHANGED, AuditAction.CYPHER_EXECUTED):
            await audit_service.record(
                organization_id=organization_id, action=action, entity_type="Application"
            )
        found = await audit_service.list_for_org(organization_id, action=AuditAction.NODE_CHANGED)
        assert [action_of(one) for one in found] == [AuditAction.NODE_CHANGED]

    async def test_entity_history_crosses_actions(
        self, audit_service: AuditService, organization_id: uuid.UUID
    ) -> None:
        for action in (AuditAction.NODE_CHANGED, AuditAction.ADMINISTRATIVE):
            await audit_service.record(
                organization_id=organization_id,
                action=action,
                entity_type="Application",
                entity_key="app-1",
            )
        assert len(await audit_service.list_for_entity(organization_id, "app-1")) == 2

    async def test_the_summary_counts_by_action_and_outcome(
        self, audit_service: AuditService, organization_id: uuid.UUID
    ) -> None:
        await audit_service.record(
            organization_id=organization_id,
            action=AuditAction.NODE_CHANGED,
            entity_type="Application",
        )
        await audit_service.record_denied(
            organization_id=organization_id,
            action=AuditAction.CYPHER_EXECUTED,
            entity_type="Cypher",
            reason="refused",
        )
        summary = await audit_service.summarise(organization_id)
        assert summary["total"] == 2
        assert summary["denied"] == 1
        assert summary["by_action"][str(AuditAction.NODE_CHANGED)] == 1

    async def test_the_summary_does_not_double_count_reloaded_rows(
        self,
        audit_service: AuditService,
        db_session: AsyncSession,
        organization_id: uuid.UUID,
    ) -> None:
        # `action` is Mapped[AuditAction] on a String column, so a row
        # loaded from Postgres yields a plain str. A summary that keyed
        # on the raw value would count the in-memory member and the
        # reloaded string as two different actions.
        stored = await audit_service.record(
            organization_id=organization_id,
            action=AuditAction.NODE_CHANGED,
            entity_type="Application",
        )
        assert stored is not None
        await db_session.refresh(stored)
        assert isinstance(stored.action, str)

        await audit_service.record(
            organization_id=organization_id,
            action=AuditAction.NODE_CHANGED,
            entity_type="Application",
        )
        summary = await audit_service.summarise(organization_id)
        assert summary["by_action"] == {str(AuditAction.NODE_CHANGED): 2}


class TestQueryServiceBuiltins:
    """The catalogue this service wrote."""

    async def test_every_catalogued_kind_runs(
        self,
        query_service: QueryService,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        # The point is that Neo4j accepts all five: they are built at
        # import time from validated fragments, so a builder change that
        # produced malformed Cypher would otherwise surface in
        # production rather than here.
        del seeded_graph
        for kind in BUILTIN_QUERIES:
            outcome = await query_service.run_builtin(
                organization_id, kind, parameters={"root_key": "app-1"}
            )
            assert outcome.kind is kind

    async def test_a_dependency_query_finds_the_dependency(
        self,
        query_service: QueryService,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        outcome = await query_service.run_builtin(
            organization_id,
            QueryKind.SERVICE_DEPENDENCY,
            parameters={"root_key": "app-1"},
        )
        assert "db-1" in {row["key"] for row in outcome.rows}

    async def test_an_uncatalogued_kind_names_the_alternatives(
        self, query_service: QueryService, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(ValidationError, match="POST /graph/cypher"):
            await query_service.run_builtin(organization_id, QueryKind.CUSTOM_CYPHER)

    async def test_a_missing_required_parameter_is_named(
        self, query_service: QueryService, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(ValidationError, match="root_key"):
            await query_service.run_builtin(organization_id, QueryKind.SERVICE_DEPENDENCY)

    async def test_an_execution_is_recorded_with_its_parameters_kept_separate(
        self,
        query_service: QueryService,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        await query_service.run_builtin(organization_id, QueryKind.OWNERSHIP)
        history = await query_service.history(organization_id)
        assert len(history) == 1
        assert history[0].succeeded is True
        # organization_id is stripped: it is scoping, not a caller input,
        # and storing it would duplicate the row's own column.
        assert "organization_id" not in (history[0].parameters or {})


class TestQueryServiceCustomCypher:
    """The security boundary, end to end through the service."""

    async def test_a_read_only_statement_runs(
        self,
        query_service: QueryService,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        outcome = await query_service.run_custom(
            organization_id,
            "MATCH (n:GraphNode {organization_id: $organization_id}) "
            "RETURN n.key AS key ORDER BY key LIMIT $limit",
        )
        assert {row["key"] for row in outcome.rows} == {
            "app-1",
            "db-1",
            "host-1",
            "vm-1",
            "vm-2",
        }

    async def test_a_write_is_refused_before_it_reaches_neo4j(
        self, query_service: QueryService, organization_id: uuid.UUID
    ) -> None:
        # Refused by the guard rather than by the database, so the caller
        # gets a message naming the clause and the refusal is auditable
        # as DENIED rather than as a driver error.
        with pytest.raises(ValidationError, match="DELETE"):
            await query_service.run_custom(organization_id, "MATCH (n:GraphNode) DETACH DELETE n")

    async def test_an_unbound_parameter_is_refused(
        self, query_service: QueryService, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(ValidationError, match="rogue"):
            await query_service.run_custom(
                organization_id, "MATCH (n:GraphNode) WHERE n.key = $rogue RETURN n LIMIT $limit"
            )

    async def test_a_refused_statement_is_never_recorded_as_executed(
        self, query_service: QueryService, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(ValidationError):
            await query_service.run_custom(organization_id, "MATCH (n) DETACH DELETE n")
        assert await query_service.history(organization_id) == []

    async def test_a_failing_statement_is_recorded_as_failed(
        self, query_service: QueryService, organization_id: uuid.UUID
    ) -> None:
        # A history containing only successes cannot answer "what has
        # been failing since the upgrade?", which is the question it is
        # usually opened for.
        # Neo4j refuses the syntax; which exception class the driver
        # raises is its business, not this test's.
        with pytest.raises(Exception, match=r"\S"):
            await query_service.run_custom(
                organization_id, "MATCH (n:GraphNode) RETURN n.key AS ((("
            )
        history = await query_service.history(organization_id, failed_only=True)
        assert len(history) == 1
        assert history[0].succeeded is False
        assert history[0].error

    async def test_custom_cypher_can_be_disabled_for_a_deployment(
        self,
        graph_client: Any,
        db_session: AsyncSession,
        organization_id: uuid.UUID,
    ) -> None:
        service = QueryService(
            graph_client,
            GraphQueryRepository(db_session),
            GraphSavedQueryRepository(db_session),
            allow_custom_cypher=False,
        )
        with pytest.raises(ConflictError, match="disabled"):
            await service.run_custom(organization_id, "MATCH (n) RETURN n LIMIT $limit")


class TestQueryServiceSavedQueries:
    """Stored queries stay parameterised through storage."""

    async def test_a_saved_query_runs_with_bound_parameters(
        self,
        query_service: QueryService,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        await query_service.save_query(
            organization_id,
            slug="by-type",
            name="Nodes by type",
            cypher=(
                "MATCH (n:GraphNode {organization_id: $organization_id}) "
                "WHERE n.node_type = $node_type RETURN n.key AS key LIMIT $limit"
            ),
            parameter_schema={"node_type": "string"},
        )
        outcome = await query_service.run_saved(
            organization_id, "by-type", parameters={"node_type": "VirtualMachine"}
        )
        assert {row["key"] for row in outcome.rows} == {"vm-1", "vm-2"}

    async def test_a_declared_parameter_that_was_not_supplied_is_named(
        self, query_service: QueryService, organization_id: uuid.UUID
    ) -> None:
        await query_service.save_query(
            organization_id,
            slug="by-type",
            name="Nodes by type",
            cypher="MATCH (n:GraphNode) WHERE n.node_type = $node_type RETURN n LIMIT $limit",
            parameter_schema={"node_type": "string"},
        )
        with pytest.raises(ValidationError, match="node_type"):
            await query_service.run_saved(organization_id, "by-type")

    async def test_defaults_fill_in_and_the_caller_overrides_them(
        self,
        query_service: QueryService,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        await query_service.save_query(
            organization_id,
            slug="by-type",
            name="Nodes by type",
            cypher=(
                "MATCH (n:GraphNode {organization_id: $organization_id}) "
                "WHERE n.node_type = $node_type RETURN n.key AS key LIMIT $limit"
            ),
            parameter_schema={"node_type": "string"},
            default_parameters={"node_type": "Application"},
        )
        defaulted = await query_service.run_saved(organization_id, "by-type")
        assert {row["key"] for row in defaulted.rows} == {"app-1"}

        overridden = await query_service.run_saved(
            organization_id, "by-type", parameters={"node_type": "Database"}
        )
        assert {row["key"] for row in overridden.rows} == {"db-1"}

    async def test_a_write_cannot_be_saved_in_the_first_place(
        self, query_service: QueryService, organization_id: uuid.UUID
    ) -> None:
        # Checked at save time as well as at execution: a statement that
        # could never run safely should be refused when someone writes
        # it, not the first time somebody else runs it.
        with pytest.raises(ValidationError):
            await query_service.save_query(
                organization_id,
                slug="dangerous",
                name="Dangerous",
                cypher="MATCH (n) DETACH DELETE n",
            )

    async def test_a_duplicate_slug_is_refused(
        self, query_service: QueryService, organization_id: uuid.UUID
    ) -> None:
        for _ in range(1):
            await query_service.save_query(
                organization_id,
                slug="dupe",
                name="First",
                cypher="MATCH (n:GraphNode) RETURN n LIMIT $limit",
            )
        with pytest.raises(ConflictError):
            await query_service.save_query(
                organization_id,
                slug="dupe",
                name="Second",
                cypher="MATCH (n:GraphNode) RETURN n LIMIT $limit",
            )

    async def test_running_a_saved_query_counts_the_execution(
        self,
        query_service: QueryService,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        await query_service.save_query(
            organization_id,
            slug="all",
            name="All",
            cypher=(
                "MATCH (n:GraphNode {organization_id: $organization_id}) "
                "RETURN n.key AS key LIMIT $limit"
            ),
        )
        await query_service.run_saved(organization_id, "all")
        await query_service.run_saved(organization_id, "all")
        saved = await query_service.list_saved(organization_id)
        assert saved[0].execution_count == 2

    async def test_an_unknown_slug_raises(
        self, query_service: QueryService, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await query_service.run_saved(organization_id, "nonexistent")

    async def test_deleting_a_saved_query(
        self, query_service: QueryService, organization_id: uuid.UUID
    ) -> None:
        await query_service.save_query(
            organization_id,
            slug="temp",
            name="Temp",
            cypher="MATCH (n:GraphNode) RETURN n LIMIT $limit",
        )
        assert await query_service.delete_saved(organization_id, "temp") is True
        assert await query_service.delete_saved(organization_id, "temp") is False

    async def test_a_system_query_cannot_be_deleted(
        self, query_service: QueryService, organization_id: uuid.UUID
    ) -> None:
        record = await query_service.save_query(
            organization_id,
            slug="system",
            name="System",
            cypher="MATCH (n:GraphNode) RETURN n LIMIT $limit",
        )
        record.is_system = True
        with pytest.raises(ConflictError, match="copy"):
            await query_service.delete_saved(organization_id, "system")

    async def test_the_slowest_queries_can_be_listed(
        self,
        query_service: QueryService,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        await query_service.run_builtin(organization_id, QueryKind.OWNERSHIP)
        assert len(await query_service.slowest(organization_id)) == 1


class TestAnalyticsService:
    """Dependency analyses and the algorithm catalogue."""

    async def test_dependencies_walk_outward(
        self,
        analytics_service: AnalyticsService,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        result = await analytics_service.dependencies(organization_id, "app-1")
        assert {one.node.key for one in result.affected} >= {"vm-1", "db-1", "host-1"}

    async def test_impact_walks_inward(
        self,
        analytics_service: AnalyticsService,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        # host-1 is depended upon by everything above it; nothing depends
        # on app-1. Getting the direction backwards would make the two
        # answers swap, which is why both are asserted.
        del seeded_graph
        result = await analytics_service.impact(organization_id, "host-1")
        assert {one.node.key for one in result.affected} >= {"vm-1", "vm-2", "app-1"}

        leaf = await analytics_service.impact(organization_id, "app-1")
        assert leaf.affected == []

    async def test_impact_is_announced_with_its_severity(
        self,
        analytics_service: AnalyticsService,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
        publisher: RecordingPublisher,
    ) -> None:
        del seeded_graph
        await analytics_service.impact(organization_id, "host-1")
        assert publisher.names == ["ImpactAnalysisCompleted"]
        assert publisher.events[0].payload["severity"] in {str(one) for one in Severity}

    async def test_blast_radius_is_announced_with_its_risk_score(
        self,
        analytics_service: AnalyticsService,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
        publisher: RecordingPublisher,
    ) -> None:
        del seeded_graph
        result = await analytics_service.blast_radius(organization_id, "host-1")
        assert publisher.names == ["BlastRadiusCalculated"]
        assert 0.0 <= result.risk_score <= 1.0

    async def test_risk_is_the_worst_single_impact_not_the_sum(
        self,
        analytics_service: AnalyticsService,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        # A sum grows with estate size, so a large healthy environment
        # would score worse than a small fragile one. Bounded at 1.0 is
        # the observable consequence of taking the maximum.
        del seeded_graph
        result = await analytics_service.blast_radius(organization_id, "host-1")
        assert result.risk_score <= 1.0
        assert result.risk_score == max(one.impact_score for one in result.affected)

    async def test_an_analysis_can_be_stored_as_a_report(
        self,
        analytics_service: AnalyticsService,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        await analytics_service.dependencies(organization_id, "app-1", store=True)
        reports = await analytics_service.reports(organization_id)
        assert [str(one.kind) for one in reports] == [str(QueryKind.DEPENDENCY_LOOKUP)]

    async def test_a_dependency_lookup_is_not_stored_by_default(
        self,
        analytics_service: AnalyticsService,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        await analytics_service.dependencies(organization_id, "app-1")
        assert await analytics_service.reports(organization_id) == []

    async def test_an_analysis_of_a_missing_root_raises(
        self,
        analytics_service: AnalyticsService,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        with pytest.raises(NotFoundError):
            await analytics_service.dependencies(organization_id, "ghost")

    @pytest.mark.parametrize("algorithm", list(AnalyticsAlgorithm))
    async def test_every_algorithm_in_the_enum_dispatches(
        self,
        algorithm: AnalyticsAlgorithm,
        analytics_service: AnalyticsService,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        # Parametrised over the enum rather than a hand-written list, so
        # adding a member without wiring it up fails here instead of
        # returning an empty result in production.
        del seeded_graph
        parameters: dict[str, Any] = {
            "from_key": "app-1",
            "to_key": "host-1",
            "root_key": "app-1",
            "failed_keys": ["host-1"],
        }
        outcome = await analytics_service.run(organization_id, algorithm, parameters=parameters)
        assert outcome.algorithm is algorithm
        assert outcome.node_count == 5

    async def test_pagerank_returns_a_ranking(
        self,
        analytics_service: AnalyticsService,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        outcome = await analytics_service.run(organization_id, AnalyticsAlgorithm.PAGERANK)
        assert outcome.ranked[0]["key"] == "host-1"

    async def test_shortest_path_needs_both_endpoints(
        self,
        analytics_service: AnalyticsService,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        with pytest.raises(ValidationError):
            await analytics_service.run(organization_id, AnalyticsAlgorithm.SHORTEST_PATH)

    async def test_a_graph_over_the_ceiling_is_refused_not_attempted(
        self,
        graph: GraphRepository,
        db_session: AsyncSession,
        organization_id: uuid.UUID,
        seeded_graph: GraphRepository,
        publisher: RecordingPublisher,
    ) -> None:
        # These algorithms need the whole graph in memory. Refusing with
        # a number beats timing out with none.
        del seeded_graph
        service = AnalyticsService(
            graph,
            GraphReportRepository(db_session),
            GraphMetadataRepository(db_session),
            DependencyEngine(graph),
            publish_event=publisher,
            max_nodes=2,
        )
        with pytest.raises(ValidationError, match="ceiling"):
            await service.run(organization_id, AnalyticsAlgorithm.DEGREE_CENTRALITY)

    async def test_declared_criticality_reaches_the_critical_asset_ranking(
        self,
        analytics_service: AnalyticsService,
        twin_service: Any,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        # Structure alone cannot know that a low-degree node is the
        # payroll database. An operator's declared criticality is the
        # only source for that, so it has to reach the ranking.
        del seeded_graph
        await twin_service.set_state(organization_id, "db-1", criticality=1.0)
        outcome = await analytics_service.run(organization_id, AnalyticsAlgorithm.CRITICAL_ASSETS)
        assert "db-1" in {row["key"] for row in outcome.ranked}


class TestStatisticsService:
    """Figures derived from the graph, never incremented."""

    async def test_the_rollup_reports_the_real_counts(
        self,
        statistics_service: StatisticsService,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        values = await statistics_service.compute(organization_id)
        assert values["node_count"] == 5
        assert values["relationship_count"] == 5

    async def test_orphans_are_counted_separately(
        self,
        statistics_service: StatisticsService,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        # Almost always a synchronization bug rather than a fact about
        # the estate, which is why it gets its own number instead of
        # hiding inside the node count.
        await seeded_graph.upsert_node(
            organization_id,
            NodeInput(key="orphan", node_type=NodeType.APPLICATION, name="orphan"),
        )
        values = await statistics_service.compute(organization_id)
        assert values["orphan_count"] == 1

    async def test_a_split_estate_shows_as_two_components(
        self,
        statistics_service: StatisticsService,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        # An estate that has quietly split into two graphs still answers
        # every single-node query correctly, so this is the figure that
        # surfaces it.
        await seeded_graph.upsert_nodes(
            organization_id,
            [
                NodeInput(key="far-1", node_type=NodeType.APPLICATION, name="far-1"),
                NodeInput(key="far-2", node_type=NodeType.VIRTUAL_MACHINE, name="far-2"),
            ],
        )
        await seeded_graph.upsert_relationship(
            organization_id,
            RelationshipInput(
                from_key="far-1", to_key="far-2", relationship_type=RelationshipType.RUNS_ON
            ),
        )
        values = await statistics_service.compute(organization_id)
        assert values["connected_components"] == 2

    async def test_average_and_max_degree_are_reported(
        self,
        statistics_service: StatisticsService,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        values = await statistics_service.compute(organization_id)
        # host-1 has two incoming edges; app-1 has two outgoing.
        assert values["max_degree"] == 2
        assert values["average_degree"] == pytest.approx(2.0)

    async def test_an_empty_graph_computes_without_dividing_by_zero(
        self, statistics_service: StatisticsService, organization_id: uuid.UUID
    ) -> None:
        values = await statistics_service.compute(organization_id)
        assert values["node_count"] == 0
        assert values["average_degree"] == 0.0
        assert values["max_degree"] == 0

    async def test_structural_analysis_is_skipped_above_the_ceiling(
        self,
        graph: GraphRepository,
        db_session: AsyncSession,
        twin_service: Any,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        # Refusing one section of a statistics response beats making the
        # whole endpoint time out on a large estate.
        del seeded_graph
        service = StatisticsService(
            graph,
            GraphStatisticsRepository(db_session),
            GraphMetadataRepository(db_session),
            GraphSyncJobRepository(db_session),
            twin_service,
            max_nodes=2,
        )
        values = await service.compute(organization_id)
        assert values["connected_components"] == 0
        assert values["node_count"] == 5  # the cheap counts still answer

    async def test_refreshing_stores_and_then_updates_in_place(
        self,
        statistics_service: StatisticsService,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        # Updated rather than appended: the graph itself is the history,
        # and a second copy of these numbers would only be another thing
        # to keep consistent.
        del seeded_graph
        first = await statistics_service.refresh(organization_id)
        second = await statistics_service.refresh(organization_id)
        assert first.id == second.id

    async def test_the_stored_rollup_can_be_read_back(
        self,
        statistics_service: StatisticsService,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        assert await statistics_service.get(organization_id) is None
        await statistics_service.refresh(organization_id)
        stored = await statistics_service.get(organization_id)
        assert stored is not None
        assert stored.node_count == 5

    async def test_sync_health_reports_healthy_when_nothing_has_failed(
        self, statistics_service: StatisticsService, organization_id: uuid.UUID
    ) -> None:
        values = await statistics_service.compute(organization_id)
        assert values["sync_health"]["healthy"] is True
        assert values["sync_health"]["failing_sources"] == []

    async def test_twin_counts_reach_the_rollup(
        self,
        statistics_service: StatisticsService,
        twin_service: Any,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        await twin_service.set_state(
            organization_id, "app-1", lifecycle_state=LifecycleState.ACTIVE
        )
        values = await statistics_service.compute(organization_id)
        assert values["twin_counts"][str(TwinType.APPLICATION)] == 1


class TestDigitalTwinService:
    """A node plus the state PostgreSQL holds about it."""

    async def test_a_twin_assembles_its_components_and_dependencies(
        self,
        twin_service: Any,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        twin = await twin_service.build(organization_id, "app-1")
        assert twin.twin_type is TwinType.APPLICATION
        # RUNS_ON counts as a dependency edge alongside DEPENDS_ON: an
        # application depends on the machine it runs on.
        assert {one.key for one in twin.dependencies} == {"db-1", "vm-1"}

    async def test_a_twin_knows_what_depends_on_it(
        self,
        twin_service: Any,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        twin = await twin_service.build(organization_id, "db-1")
        assert {one.key for one in twin.dependents} == {"app-1"}

    async def test_state_survives_a_rebuild(
        self,
        twin_service: Any,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        await twin_service.set_state(
            organization_id,
            "app-1",
            lifecycle_state=LifecycleState.ACTIVE,
            criticality=0.8,
            owner_team="platform",
            tags=["billing"],
        )
        twin = await twin_service.build(organization_id, "app-1")
        assert twin.criticality == 0.8
        assert twin.owner_team == "platform"
        assert twin.tags == ["billing"]

    async def test_criticality_is_clamped_to_the_unit_interval(
        self,
        twin_service: Any,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        stored = await twin_service.set_state(organization_id, "app-1", criticality=5.0)
        assert stored.criticality == 1.0

    async def test_state_for_a_missing_node_is_refused(
        self, twin_service: Any, organization_id: uuid.UUID
    ) -> None:
        # Metadata for a node that is not in the graph would be
        # unreachable by every read path that joins on the node key.
        with pytest.raises(NotFoundError):
            await twin_service.set_state(organization_id, "ghost", criticality=0.5)

    async def test_a_twins_health_is_the_worst_of_its_components(
        self,
        twin_service: Any,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        # A host reporting healthy while a VM it contains is unhealthy is
        # not healthy in any sense an operator means.
        #
        # Containment is a different edge set from dependency: RUNS_ON
        # makes vm-1 depend on host-1, but only PART_OF makes it a
        # *component* of it, and only components compose health.
        await seeded_graph.upsert_relationship(
            organization_id,
            RelationshipInput(
                from_key="vm-1", to_key="host-1", relationship_type=RelationshipType.PART_OF
            ),
        )
        await twin_service.set_state(organization_id, "host-1", health_status=HealthStatus.HEALTHY)
        await twin_service.set_state(organization_id, "vm-1", health_status=HealthStatus.UNHEALTHY)
        twin = await twin_service.build(organization_id, "host-1")
        assert twin.health is HealthStatus.UNHEALTHY

    async def test_a_degraded_lifecycle_overrides_a_healthy_check(
        self,
        twin_service: Any,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        await twin_service.set_state(
            organization_id,
            "app-1",
            lifecycle_state=LifecycleState.RETIRING,
            health_status=HealthStatus.HEALTHY,
        )
        twin = await twin_service.build(organization_id, "app-1")
        assert twin.health is HealthStatus.DEGRADED
        # Lifecycle and health both have to hold; RETIRING fails the first.
        assert twin.is_operational is False

    async def test_an_unhealthy_twin_is_not_operational(
        self,
        twin_service: Any,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        await twin_service.set_state(organization_id, "app-1", health_status=HealthStatus.UNHEALTHY)
        twin = await twin_service.build(organization_id, "app-1")
        assert twin.is_operational is False

    async def test_building_a_twin_for_a_missing_node_raises(
        self, twin_service: Any, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await twin_service.build(organization_id, "ghost")

    async def test_twins_can_be_filtered_by_lifecycle(
        self,
        twin_service: Any,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        await twin_service.set_state(
            organization_id, "app-1", lifecycle_state=LifecycleState.ACTIVE
        )
        await twin_service.set_state(
            organization_id, "vm-1", lifecycle_state=LifecycleState.RETIRING
        )
        active = await twin_service.list_twins(
            organization_id, lifecycle_state=LifecycleState.ACTIVE
        )
        assert [one.node_key for one in active] == ["app-1"]

    async def test_a_twins_dict_form_is_serialisable(
        self,
        twin_service: Any,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        twin = await twin_service.build(organization_id, "app-1")
        payload = twin.as_dict()
        assert payload["node"]["key"] == "app-1"
        assert payload["twin_type"] == str(TwinType.APPLICATION)
        assert isinstance(payload["component_count"], int)
        # Serialisable for real, not merely dict-shaped: a Neo4j
        # DateTime left in a property dict encodes fine as a repr and
        # fails only at json.dumps.
        assert json.loads(json.dumps(payload))["node"]["key"] == "app-1"
