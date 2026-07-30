"""Synchronization, snapshots, and search.

Three subjects that share a property: each one is destructive or
lossy if it is subtly wrong, and each one looks like it is working
while it is. A sync that deletes the nodes it should have kept, a
snapshot that restores an empty graph, a search that quietly drops a
tenant scope -- none of them raises.

The mappers are tested as pure functions against fixed payloads, which
is what they were written as. Everything below them runs against real
PostgreSQL and real Neo4j.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

import httpx
import pytest
from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError
from shared_core.exceptions.validation import ValidationError

from app.clients.platform import PlatformSourceClient, SourceEndpoints
from app.graph.entities import GraphNode, NodeInput, RelationshipInput, Subgraph
from app.graph.repository import GraphRepository
from app.models.enums import (
    ConflictResolution,
    GraphFormat,
    JobStatus,
    NodeType,
    RelationshipType,
    SyncMode,
    SyncSource,
    SyncStatus,
)
from app.repositories.graph_change_history import GraphChangeHistoryRepository
from app.repositories.graph_metadata import GraphMetadataRepository
from app.repositories.graph_snapshot import GraphSnapshotRepository
from app.repositories.graph_sync_job import GraphSyncJobRepository
from app.repositories.graph_version import GraphVersionRepository
from app.search.engine import (
    SORTABLE_FIELDS,
    SearchEngine,
    build_search_term,
    escape_lucene,
)
from app.services.sync import SyncService
from app.synchronization.engine import (
    MAX_PAGES,
    SynchronizationEngine,
    mode_of,
    resolution_of,
    source_of,
    status_of,
)
from app.synchronization.mappers import (
    MAPPERS,
    SOURCE_PATHS,
    MappedBatch,
    classify_asset,
    map_inventory,
    map_rows,
    pick,
    scoped_key,
)
from app.versioning.snapshots import SnapshotService, _as_graph_relationship, compare
from tests.conftest import SAMPLE_ASSETS, source_handler, utcnow

# No module-level asyncio mark: this file mixes pure mapper tests with
# async ones, and `asyncio_mode = "auto"` already collects the async
# ones. Marking a sync test asyncio is a warning, which this suite
# turns into a failure.


def node(key: str, name: str = "n", node_type: str = "Application", **kwargs: Any) -> GraphNode:
    """A minimal node for diff fixtures."""
    return GraphNode(key=key, node_type=node_type, name=name, organization_id="org", **kwargs)


class TestMapperTables:
    """The dispatch tables every sync depends on."""

    @pytest.mark.parametrize("source", list(SyncSource))
    def test_every_source_has_a_mapper(self, source: SyncSource) -> None:
        # A source declared in the enum with no mapper is silently
        # skipped by the engine -- the sync reports success and the
        # graph is simply missing that whole domain.
        assert source in MAPPERS

    @pytest.mark.parametrize("source", list(SyncSource))
    def test_every_source_has_an_endpoint(self, source: SyncSource) -> None:
        assert source in SOURCE_PATHS

    def test_an_unknown_source_maps_to_nothing_rather_than_raising(self) -> None:
        # The engine iterates a configured list; one unmapped source must
        # not abort a whole run.
        assert map_rows("not-a-source", [{"id": "1"}]).is_empty  # type: ignore[arg-type]


class TestKeyScoping:
    """Two sources cannot collide on one node."""

    def test_keys_are_namespaced_by_source(self) -> None:
        # Inventory asset 42 and automation job 42 are different things.
        # Without the prefix they merge into one node and the graph is
        # confidently wrong in a way no error surfaces.
        assert scoped_key(SyncSource.INVENTORY, "42") != scoped_key(SyncSource.AUTOMATION, "42")

    def test_the_identifier_field_is_found_under_any_of_its_names(self) -> None:
        # The platform's services settled on different names for the same
        # idea; this is the accommodation, in preference order.
        assert pick({"id": "a", "uuid": "b"}, ("key", "id", "uuid")) == "a"
        assert pick({"uuid": "b"}, ("key", "id", "uuid")) == "b"

    def test_an_empty_value_is_not_a_key(self) -> None:
        assert pick({"key": "", "id": "real"}, ("key", "id")) == "real"

    def test_a_row_with_no_identity_is_rejected_not_invented(self) -> None:
        # A node with no stable key cannot be merged, matched, or joined
        # to its metadata.
        batch = map_inventory([{"name": "nameless"}])
        assert batch.nodes == []
        assert len(batch.rejections) == 1
        assert "stable identifier" in batch.rejections[0]["reason"]


class TestAssetClassification:
    """Source type strings to graph labels."""

    @pytest.mark.parametrize(
        ("declared", "expected"),
        [
            ("virtual_machine", NodeType.VIRTUAL_MACHINE),
            ("vm", NodeType.VIRTUAL_MACHINE),
            ("physical_server", NodeType.PHYSICAL_SERVER),
            ("database", NodeType.DATABASE),
            ("plc", NodeType.PLC),
        ],
    )
    def test_known_types_map_to_their_label(self, declared: str, expected: NodeType) -> None:
        assert classify_asset({"asset_type": declared}) is expected

    def test_an_unknown_type_becomes_an_unclassified_node(self) -> None:
        # Deliberate: a new asset kind in inventory should appear in the
        # graph as unclassified, not vanish from it, and not silently
        # take another type's label.
        assert classify_asset({"asset_type": "quantum_widget"}) is NodeType.CUSTOM_NODE

    def test_classification_is_case_insensitive(self) -> None:
        assert classify_asset({"asset_type": "Virtual_Machine"}) is NodeType.VIRTUAL_MACHINE

    def test_the_type_is_read_from_any_of_its_field_names(self) -> None:
        assert classify_asset({"type": "database"}) is NodeType.DATABASE
        assert classify_asset({"kind": "database"}) is NodeType.DATABASE


class TestInventoryMapping:
    """The mapper the rest of the graph hangs off."""

    def test_assets_become_nodes_and_their_hosts_become_edges(self) -> None:
        batch = map_inventory(SAMPLE_ASSETS)
        assert len(batch.nodes) == 3
        assert batch.relationships != []

    def test_a_projected_node_carries_only_the_narrow_field_set(self) -> None:
        # Synchronization reads with a *service* token, so a mapper that
        # copied whole source rows would launder privileged data into a
        # store with different access rules.
        batch = map_inventory(
            [
                {
                    "id": "vm-1",
                    "name": "vm-1",
                    "asset_type": "virtual_machine",
                    "environment": "prod",
                    "root_password": "hunter2",
                    "ssh_private_key": "-----BEGIN",
                }
            ]
        )
        stored = batch.nodes[0]
        assert "root_password" not in stored.properties
        assert "ssh_private_key" not in stored.properties
        assert stored.properties["environment"] == "prod"

    def test_a_self_referencing_row_drops_the_edge_not_the_node(self) -> None:
        # A self-loop makes every dependency traversal cyclic. The entity
        # model refuses it outright, so the mapper drops it here rather
        # than letting one bad row abort a whole page.
        batch = map_inventory(
            [{"id": "vm-1", "name": "vm-1", "asset_type": "virtual_machine", "host_id": "vm-1"}]
        )
        assert len(batch.nodes) == 1
        assert batch.relationships == []

    @pytest.mark.parametrize("source", list(SyncSource))
    def test_no_mapper_raises_on_a_junk_page(self, source: SyncSource) -> None:
        # Every mapper has to survive a source that changed its payload
        # shape: one bad page must not take down the whole sync.
        batch = map_rows(source, [{}, {"unexpected": None}, {"id": "x"}])
        assert isinstance(batch, MappedBatch)

    @pytest.mark.parametrize("source", list(SyncSource))
    def test_every_mapper_scopes_the_keys_it_produces(self, source: SyncSource) -> None:
        batch = map_rows(source, [{"id": "shared-42", "name": "thing"}])
        for stored in batch.nodes:
            assert stored.key.startswith(f"{source}:")


class TestSynchronizationEngine:
    """Pulling a source into the graph."""

    async def test_a_source_syncs_into_the_graph(
        self,
        sync_engine: SynchronizationEngine,
        graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        job = await sync_engine.sync_source(organization_id, SyncSource.INVENTORY)
        assert status_of(job) is SyncStatus.SUCCEEDED
        assert job.nodes_created == 3
        assert await graph.count_nodes(organization_id) == 3

    async def test_syncing_twice_updates_rather_than_duplicating(
        self,
        sync_engine: SynchronizationEngine,
        graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        # The property the whole design rests on: MERGE on
        # (key, organization_id) means a re-run is an update.
        for _ in range(2):
            await sync_engine.sync_source(organization_id, SyncSource.INVENTORY)
        assert await graph.count_nodes(organization_id) == 3

    async def test_a_failing_source_is_recorded_not_raised(
        self,
        graph: GraphRepository,
        db_session: Any,
        source_endpoints: SourceEndpoints,
        organization_id: uuid.UUID,
    ) -> None:
        # A caller syncing ten sources needs the other nine to proceed.
        engine = await _engine_with_handler(
            graph, db_session, source_endpoints, source_handler(status_code=503)
        )
        job = await engine.sync_source(organization_id, SyncSource.INVENTORY)
        assert status_of(job) is SyncStatus.FAILED
        assert job.error

    async def test_repeated_failures_disable_the_source(
        self,
        graph: GraphRepository,
        db_session: Any,
        source_endpoints: SourceEndpoints,
        organization_id: uuid.UUID,
    ) -> None:
        # Retrying a permanently broken source every five minutes forever
        # fills the log and buries the real problem.
        engine = await _engine_with_handler(
            graph, db_session, source_endpoints, source_handler(status_code=503), max_failures=3
        )
        for _ in range(3):
            job = await engine.sync_source(organization_id, SyncSource.INVENTORY)
        assert status_of(job) is SyncStatus.DISABLED

    async def test_a_disabled_source_is_skipped_without_a_new_job(
        self,
        graph: GraphRepository,
        db_session: Any,
        source_endpoints: SourceEndpoints,
        organization_id: uuid.UUID,
    ) -> None:
        engine = await _engine_with_handler(
            graph, db_session, source_endpoints, source_handler(status_code=503), max_failures=1
        )
        disabled = await engine.sync_source(organization_id, SyncSource.INVENTORY)
        assert status_of(disabled) is SyncStatus.DISABLED
        again = await engine.sync_source(organization_id, SyncSource.INVENTORY)
        assert again.id == disabled.id

    async def test_a_successful_run_clears_the_failure_count(
        self,
        sync_engine: SynchronizationEngine,
        organization_id: uuid.UUID,
    ) -> None:
        job = await sync_engine.sync_source(organization_id, SyncSource.INVENTORY)
        assert job.consecutive_failures == 0

    async def test_an_incremental_run_stores_a_cursor(
        self, sync_engine: SynchronizationEngine, organization_id: uuid.UUID
    ) -> None:
        job = await sync_engine.sync_source(
            organization_id, SyncSource.INVENTORY, mode=SyncMode.INCREMENTAL
        )
        # The newest updated_at across the page, so the next run asks for
        # only what changed after it.
        assert job.cursor == "2026-07-03T10:00:00Z"

    async def test_syncing_every_source_returns_a_job_each(
        self, sync_engine: SynchronizationEngine, organization_id: uuid.UUID
    ) -> None:
        jobs = await sync_engine.sync_all(organization_id)
        assert len(jobs) == len(SyncSource)

    async def test_a_selected_subset_syncs_only_those(
        self, sync_engine: SynchronizationEngine, organization_id: uuid.UUID
    ) -> None:
        jobs = await sync_engine.sync_all(
            organization_id, sources=[SyncSource.INVENTORY, SyncSource.DISCOVERY]
        )
        assert {source_of(one) for one in jobs} == {SyncSource.INVENTORY, SyncSource.DISCOVERY}

    async def test_the_page_ceiling_makes_a_run_partial_not_endless(
        self,
        graph: GraphRepository,
        db_session: Any,
        source_endpoints: SourceEndpoints,
        organization_id: uuid.UUID,
    ) -> None:
        # A source that returns a full page forever would otherwise loop
        # until something else broke. Reported as PARTIAL, which is a
        # different and honest answer from SUCCEEDED.
        def _endless(request: httpx.Request) -> httpx.Response:
            offset = int(request.url.params.get("offset", 0))
            rows = [
                {"id": f"a-{offset + i}", "name": "x", "asset_type": "virtual_machine"}
                for i in range(2)
            ]
            return httpx.Response(200, json={"success": True, "data": rows})

        engine = await _engine_with_handler(
            graph, db_session, source_endpoints, _endless, batch_size=2
        )
        job = await engine.sync_source(organization_id, SyncSource.INVENTORY)
        assert status_of(job) is SyncStatus.PARTIAL
        assert job.nodes_created == MAX_PAGES * 2


class TestFullSyncDeletion:
    """The destructive path, and both of its guards."""

    async def test_a_full_sync_removes_what_the_source_no_longer_reports(
        self,
        sync_engine: SynchronizationEngine,
        graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        await sync_engine.sync_source(organization_id, SyncSource.INVENTORY, mode=SyncMode.FULL)
        assert await graph.count_nodes(organization_id) == 3

        stale = scoped_key(SyncSource.INVENTORY, "decommissioned")
        await graph.upsert_node(
            organization_id,
            NodeInput(key=stale, node_type=NodeType.VIRTUAL_MACHINE, name="gone"),
            source=str(SyncSource.INVENTORY),
        )
        job = await sync_engine.sync_source(
            organization_id, SyncSource.INVENTORY, mode=SyncMode.FULL
        )
        assert job.nodes_deleted == 1
        assert await graph.get_node(organization_id, stale) is None

    async def test_deletion_never_crosses_into_another_source(
        self,
        sync_engine: SynchronizationEngine,
        graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        # Unscoped, a full inventory sync would delete every automation
        # and workflow node in the graph -- and it would look exactly
        # like a working sync until someone noticed half the graph gone.
        other = scoped_key(SyncSource.AUTOMATION, "job-1")
        await graph.upsert_node(
            organization_id,
            NodeInput(key=other, node_type=NodeType.AUTOMATION_JOB, name="nightly"),
            source=str(SyncSource.AUTOMATION),
        )
        await sync_engine.sync_source(organization_id, SyncSource.INVENTORY, mode=SyncMode.FULL)
        assert await graph.get_node(organization_id, other) is not None

    async def test_a_pinned_node_survives_a_full_sync(
        self,
        sync_engine: SynchronizationEngine,
        twin_service: Any,
        graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        # Pinning is how an operator says "this is real even though the
        # source cannot see it" -- a network device behind a firewall the
        # scanner cannot reach.
        pinned = scoped_key(SyncSource.INVENTORY, "hand-added")
        await graph.upsert_node(
            organization_id,
            NodeInput(key=pinned, node_type=NodeType.FIREWALL, name="edge-fw"),
            source=str(SyncSource.INVENTORY),
        )
        await twin_service.set_state(organization_id, pinned, is_pinned=True)

        job = await sync_engine.sync_source(
            organization_id, SyncSource.INVENTORY, mode=SyncMode.FULL
        )
        assert job.nodes_deleted == 0
        assert await graph.get_node(organization_id, pinned) is not None

    async def test_an_incremental_sync_deletes_nothing(
        self,
        sync_engine: SynchronizationEngine,
        graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        # An incremental run sees only what changed, so absence from the
        # page means nothing at all about whether the node still exists.
        stale = scoped_key(SyncSource.INVENTORY, "old")
        await graph.upsert_node(
            organization_id,
            NodeInput(key=stale, node_type=NodeType.VIRTUAL_MACHINE, name="old"),
            source=str(SyncSource.INVENTORY),
        )
        job = await sync_engine.sync_source(
            organization_id, SyncSource.INVENTORY, mode=SyncMode.INCREMENTAL
        )
        assert job.nodes_deleted == 0
        assert await graph.get_node(organization_id, stale) is not None


class TestConflictResolution:
    """Which side wins one disagreement."""

    async def test_source_wins(self, sync_engine: SynchronizationEngine) -> None:
        assert (
            await sync_engine.resolve_conflict(
                policy=ConflictResolution.SOURCE_WINS, source_value="s", graph_value="g"
            )
            == "s"
        )

    async def test_graph_wins(self, sync_engine: SynchronizationEngine) -> None:
        assert (
            await sync_engine.resolve_conflict(
                policy=ConflictResolution.GRAPH_WINS, source_value="s", graph_value="g"
            )
            == "g"
        )

    async def test_newest_wins_compares_the_timestamps(
        self, sync_engine: SynchronizationEngine
    ) -> None:
        now = utcnow()
        older, newer = now - timedelta(hours=1), now
        assert (
            await sync_engine.resolve_conflict(
                policy=ConflictResolution.NEWEST_WINS,
                source_value="s",
                graph_value="g",
                source_updated=newer,
                graph_updated=older,
            )
            == "s"
        )
        assert (
            await sync_engine.resolve_conflict(
                policy=ConflictResolution.NEWEST_WINS,
                source_value="s",
                graph_value="g",
                source_updated=older,
                graph_updated=newer,
            )
            == "g"
        )

    async def test_newest_wins_without_timestamps_falls_back_to_the_source(
        self, sync_engine: SynchronizationEngine
    ) -> None:
        # Without both timestamps "newest" is unanswerable, so it falls
        # back rather than guessing.
        assert (
            await sync_engine.resolve_conflict(
                policy=ConflictResolution.NEWEST_WINS, source_value="s", graph_value="g"
            )
            == "s"
        )

    async def test_manual_keeps_the_graph_and_leaves_it_for_a_person(
        self, sync_engine: SynchronizationEngine
    ) -> None:
        # It is the policy for fields nobody wants a machine deciding, so
        # silently taking either side would defeat the point of choosing
        # it.
        assert (
            await sync_engine.resolve_conflict(
                policy=ConflictResolution.MANUAL, source_value="s", graph_value="g"
            )
            == "g"
        )


class TestSyncService:
    """Synchronization plus what it announces."""

    async def test_a_sync_announces_itself(
        self, sync_service: SyncService, organization_id: uuid.UUID, publisher: Any
    ) -> None:
        await sync_service.sync_source(organization_id, SyncSource.INVENTORY)
        assert "GraphSynchronized" in publisher.names

    async def test_a_successful_sync_records_a_version(
        self,
        sync_service: SyncService,
        snapshot_service: SnapshotService,
        organization_id: uuid.UUID,
    ) -> None:
        # One marker for the whole run rather than one per source: a
        # version describes the graph, and the graph only reaches its new
        # shape once every source has finished. So it is sync_all's job.
        outcome = await sync_service.sync_all(organization_id, sources=[SyncSource.INVENTORY])
        assert outcome["version_sequence"] == 1
        versions = await snapshot_service.list_versions(organization_id)
        assert len(versions) == 1
        assert versions[0].node_count == 3

    async def test_history_reports_what_ran(
        self, sync_service: SyncService, organization_id: uuid.UUID
    ) -> None:
        await sync_service.sync_source(organization_id, SyncSource.INVENTORY)
        history = await sync_service.history(organization_id)
        assert [source_of(one) for one in history] == [SyncSource.INVENTORY]

    async def test_resetting_a_source_clears_its_disabled_state(
        self,
        graph: GraphRepository,
        db_session: Any,
        source_endpoints: SourceEndpoints,
        snapshot_service: SnapshotService,
        notifications: Any,
        publisher: Any,
        organization_id: uuid.UUID,
    ) -> None:
        # Otherwise a source disabled at 03:00 stays disabled until
        # someone edits the database by hand.
        engine = await _engine_with_handler(
            graph, db_session, source_endpoints, source_handler(status_code=503), max_failures=1
        )
        service = SyncService(
            engine,
            GraphSyncJobRepository(db_session),
            snapshot_service,
            notifications,
            publish_event=publisher,
        )
        disabled = await service.sync_source(organization_id, SyncSource.INVENTORY)
        assert status_of(disabled) is SyncStatus.DISABLED

        reset = await service.reset_source(organization_id, SyncSource.INVENTORY)
        assert reset is not None
        assert status_of(reset) is not SyncStatus.DISABLED
        assert reset.consecutive_failures == 0

    async def test_resetting_a_source_that_never_ran_reports_nothing(
        self, sync_service: SyncService, organization_id: uuid.UUID
    ) -> None:
        assert await sync_service.reset_source(organization_id, SyncSource.WORKFLOW) is None


class TestEnumNormalisers:
    """Rows come back from Postgres as strings, not enum members."""

    async def test_a_reloaded_job_still_answers_as_enums(
        self,
        sync_engine: SynchronizationEngine,
        db_session: Any,
        organization_id: uuid.UUID,
    ) -> None:
        # `status` is Mapped[SyncStatus] on a String column, so a genuine
        # reload yields a plain str. Comparing that with `is` against an
        # enum member is always False -- silently.
        job = await sync_engine.sync_source(organization_id, SyncSource.INVENTORY)
        await db_session.refresh(job)
        assert isinstance(job.status, str)
        assert status_of(job) is SyncStatus.SUCCEEDED
        assert source_of(job) is SyncSource.INVENTORY
        assert mode_of(job) is SyncMode.INCREMENTAL
        assert resolution_of(job) is ConflictResolution.SOURCE_WINS


class TestGraphComparison:
    """Diffing two graphs."""

    def test_identical_graphs_diff_to_nothing(self) -> None:
        graph = Subgraph(nodes=[node("a"), node("b")])
        assert compare(graph, graph).is_empty

    def test_additions_and_removals_are_both_reported(self) -> None:
        before = Subgraph(nodes=[node("a"), node("b")])
        after = Subgraph(nodes=[node("b"), node("c")])
        diff = compare(before, after)
        assert diff.added_nodes == ["c"]
        assert diff.removed_nodes == ["a"]

    def test_a_changed_node_names_the_fields_that_moved(self) -> None:
        # Not both copies of everything: a diff that echoes whole nodes
        # is unreadable at the size a real graph reaches.
        before = Subgraph(nodes=[node("a", name="Old")])
        after = Subgraph(nodes=[node("a", name="New")])
        diff = compare(before, after)
        assert diff.changed_nodes == [{"key": "a", "changed": ["name"]}]

    def test_a_property_change_is_detected(self) -> None:
        before = Subgraph(nodes=[node("a", properties={"tier": "gold"})])
        after = Subgraph(nodes=[node("a", properties={"tier": "silver"})])
        assert compare(before, after).changed_nodes[0]["changed"] == ["properties"]

    def test_relationship_changes_are_reported_by_key(self) -> None:
        edge = RelationshipInput(
            from_key="a", to_key="b", relationship_type=RelationshipType.DEPENDS_ON
        )
        after = Subgraph(nodes=[node("a"), node("b")], relationships=[_as_graph_relationship(edge)])
        diff = compare(Subgraph(nodes=[node("a"), node("b")]), after)
        assert diff.added_relationships == ["a|DEPENDS_ON|b"]

    def test_the_dict_form_totals_the_changes(self) -> None:
        before = Subgraph(nodes=[node("a")])
        after = Subgraph(nodes=[node("b")])
        payload = compare(before, after).as_dict()
        assert payload["total_changes"] == 2
        assert payload["identical"] is False


class TestSnapshots:
    """Capture, restore, and what stands between them."""

    async def test_a_snapshot_captures_the_graph(
        self,
        snapshot_service: SnapshotService,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        record = await snapshot_service.capture(organization_id, label="nightly")
        assert record.status is JobStatus.SUCCEEDED or str(record.status) == str(
            JobStatus.SUCCEEDED
        )
        assert record.node_count == 5
        assert record.relationship_count == 5
        assert record.payload is not None
        assert record.checksum_sha256

    async def test_the_payload_is_compressed(
        self,
        snapshot_service: SnapshotService,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        # Payloads are the largest rows this service writes.
        del seeded_graph
        record = await snapshot_service.capture(organization_id, label="nightly")
        assert record.details["compression_ratio"] < 1.0

    async def test_a_restore_brings_the_graph_back(
        self,
        snapshot_service: SnapshotService,
        seeded_graph: GraphRepository,
        graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        # The end-to-end proof that export and import agree. Three
        # separate round-trip bugs made this fail silently before -- the
        # restore "succeeded" and left an emptier graph.
        del seeded_graph
        record = await snapshot_service.capture(organization_id, label="before")
        await graph.delete_node(organization_id, "vm-1")
        await graph.delete_node(organization_id, "db-1")
        assert await graph.count_nodes(organization_id) == 3

        result = await snapshot_service.restore(organization_id, record.id)
        assert await graph.count_nodes(organization_id) == 5
        assert await graph.count_relationships(organization_id) == 5
        assert result["restored_nodes"] == 5
        assert result["restored_relationships"] == 5
        assert result["rejected"] == 0, "the service must be able to re-read its own export"

    @pytest.mark.parametrize("snapshot_format", list(GraphFormat))
    async def test_every_format_round_trips_through_a_restore(
        self,
        snapshot_format: GraphFormat,
        snapshot_service: SnapshotService,
        seeded_graph: GraphRepository,
        graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        # Parametrised over the enum: a format that can be written but
        # not read back makes restore a dead end for anyone who chose it.
        del seeded_graph
        record = await snapshot_service.capture(
            organization_id, label="fmt", snapshot_format=snapshot_format
        )
        await graph.purge_organization(organization_id)
        assert await graph.count_nodes(organization_id) == 0

        await snapshot_service.restore(organization_id, record.id)
        assert await graph.count_nodes(organization_id) == 5

    async def test_a_restore_replaces_rather_than_merges(
        self,
        snapshot_service: SnapshotService,
        seeded_graph: GraphRepository,
        graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        # Merging would leave behind exactly what someone restoring is
        # trying to remove.
        del seeded_graph
        record = await snapshot_service.capture(organization_id, label="before")
        await graph.upsert_node(
            organization_id,
            NodeInput(key="added-later", node_type=NodeType.APPLICATION, name="oops"),
        )
        await snapshot_service.restore(organization_id, record.id)
        assert await graph.get_node(organization_id, "added-later") is None

    async def test_a_tampered_payload_is_refused(
        self,
        snapshot_service: SnapshotService,
        seeded_graph: GraphRepository,
        db_session: Any,
        organization_id: uuid.UUID,
    ) -> None:
        # The checksum is the only thing between a corrupted row and a
        # destructive restore that writes garbage over a live graph.
        del seeded_graph
        record = await snapshot_service.capture(organization_id, label="nightly")
        record.checksum_sha256 = "0" * 64
        await db_session.flush()
        with pytest.raises(ConflictError, match="checksum"):
            await snapshot_service.restore(organization_id, record.id)

    async def test_an_unfinished_snapshot_cannot_be_restored(
        self,
        snapshot_service: SnapshotService,
        seeded_graph: GraphRepository,
        db_session: Any,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        record = await snapshot_service.capture(organization_id, label="nightly")
        record.status = JobStatus.FAILED
        await db_session.flush()
        with pytest.raises(ConflictError):
            await snapshot_service.restore(organization_id, record.id)

    async def test_restoring_an_unknown_snapshot_raises(
        self, snapshot_service: SnapshotService, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await snapshot_service.restore(organization_id, uuid.uuid4())

    async def test_a_graph_over_the_ceiling_is_refused(
        self,
        graph: GraphRepository,
        db_session: Any,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        service = SnapshotService(
            graph,
            GraphSnapshotRepository(db_session),
            GraphVersionRepository(db_session),
            max_nodes=2,
        )
        with pytest.raises(ValidationError, match="ceiling"):
            await service.capture(organization_id, label="too-big")

    async def test_comparing_a_snapshot_to_the_current_graph(
        self,
        snapshot_service: SnapshotService,
        seeded_graph: GraphRepository,
        graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        # The question an operator actually asks: what has changed since
        # the snapshot?
        del seeded_graph
        record = await snapshot_service.capture(organization_id, label="before")
        await graph.upsert_node(
            organization_id,
            NodeInput(key="new-app", node_type=NodeType.APPLICATION, name="new"),
        )
        diff = await snapshot_service.compare_to_current(organization_id, record.id)
        assert diff.added_nodes == ["new-app"]

    async def test_comparing_two_snapshots(
        self,
        snapshot_service: SnapshotService,
        seeded_graph: GraphRepository,
        graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        before = await snapshot_service.capture(organization_id, label="before")
        await graph.delete_node(organization_id, "vm-2")
        after = await snapshot_service.capture(organization_id, label="after")

        diff = await snapshot_service.compare_snapshots(
            organization_id, before_id=before.id, after_id=after.id
        )
        assert diff.removed_nodes == ["vm-2"]

    async def test_snapshots_and_versions_can_be_listed(
        self,
        snapshot_service: SnapshotService,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        await snapshot_service.capture(organization_id, label="one")
        await snapshot_service.create_version(organization_id, label="v1")
        assert len(await snapshot_service.list_snapshots(organization_id)) == 1
        assert len(await snapshot_service.list_versions(organization_id)) == 1

    async def test_versions_are_sequenced(
        self,
        snapshot_service: SnapshotService,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        first = await snapshot_service.create_version(organization_id, label="v1")
        second = await snapshot_service.create_version(organization_id, label="v2")
        assert second.sequence == first.sequence + 1

    async def test_sweeping_removes_only_expired_snapshots(
        self,
        graph: GraphRepository,
        db_session: Any,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        # An unswept retention window is the thing that fills the disk.
        del seeded_graph
        expiring = SnapshotService(
            graph,
            GraphSnapshotRepository(db_session),
            GraphVersionRepository(db_session),
            retention_days=-1,
        )
        keeping = SnapshotService(
            graph,
            GraphSnapshotRepository(db_session),
            GraphVersionRepository(db_session),
            retention_days=90,
        )
        await expiring.capture(organization_id, label="old")
        await keeping.capture(organization_id, label="current")

        assert await keeping.sweep_expired(organization_id) == 1
        remaining = await keeping.list_snapshots(organization_id)
        assert [one.label for one in remaining] == ["current"]

    async def test_sweeping_nothing_is_a_no_op(
        self, snapshot_service: SnapshotService, organization_id: uuid.UUID
    ) -> None:
        assert await snapshot_service.sweep_expired(organization_id) == 0


class TestLuceneEscaping:
    """Search input reaches a query language of its own."""

    @pytest.mark.parametrize(
        "character",
        [
            "+",
            "-",
            "&",
            "|",
            "!",
            "(",
            ")",
            "{",
            "}",
            "[",
            "]",
            "^",
            '"',
            "~",
            "*",
            "?",
            ":",
            "\\",
            "/",
        ],
    )
    def test_every_lucene_metacharacter_is_escaped(self, character: str) -> None:
        # Not injection into Cypher -- the term is bound -- but a user
        # searching for "C++" would otherwise get a Lucene parse error
        # instead of a result.
        assert escape_lucene(f"a{character}b") == f"a\\{character}b"

    def test_ordinary_text_is_left_alone(self) -> None:
        assert escape_lucene("billing database") == "billing database"

    def test_a_fuzzy_term_allows_one_edit_per_word(self) -> None:
        # One character: enough for a typo, not enough to match an
        # unrelated host.
        assert build_search_term("billing", fuzzy=True) == "billing~1"

    def test_multiple_words_are_anded_so_a_search_narrows(self) -> None:
        assert build_search_term("billing db") == "billing AND db"

    def test_a_fuzzy_term_is_still_escaped(self) -> None:
        # The escaping has to happen before the tilde is appended, or the
        # tilde itself gets escaped and the search stops being fuzzy.
        assert build_search_term("C++", fuzzy=True) == "C\\+\\+~1"

    def test_an_empty_query_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            build_search_term("   ")


class TestSearch:
    """Finding nodes, against a real full-text index."""

    async def test_a_node_is_found_by_name(
        self,
        search_engine: SearchEngine,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        results = await search_engine.search(organization_id, "Billing")
        assert "app-1" in {hit.node.key for hit in results.hits}

    async def test_search_is_scoped_to_one_organization(
        self,
        search_engine: SearchEngine,
        seeded_graph: GraphRepository,
        graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        # The full-text index is global; the tenant scope is a WHERE
        # clause on top of it, which is exactly the kind of filter that
        # is easy to drop and impossible to notice.
        del seeded_graph
        other = uuid.uuid4()
        try:
            results = await search_engine.search(other, "Billing")
            assert results.hits == []
        finally:
            await graph.purge_organization(other)

    async def test_results_can_be_narrowed_by_node_type(
        self,
        search_engine: SearchEngine,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        results = await search_engine.search(
            organization_id, "vm", node_types=[NodeType.VIRTUAL_MACHINE]
        )
        assert all(hit.node.node_type == "VirtualMachine" for hit in results.hits)

    async def test_a_property_search_matches_exactly(
        self,
        search_engine: SearchEngine,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        results = await search_engine.search_by_property(
            organization_id, property_name="node_type", value="Database"
        )
        assert [hit.node.key for hit in results.hits] == ["db-1"]

    async def test_a_property_name_that_is_not_an_identifier_is_refused(
        self, search_engine: SearchEngine, organization_id: uuid.UUID
    ) -> None:
        # The property *name* is part of the query text and cannot be
        # bound, so it is validated as an identifier. This is the one
        # place in search where injection would otherwise be possible.
        with pytest.raises(ValidationError):
            await search_engine.search_by_property(
                organization_id, property_name="key} ) DETACH DELETE n //", value="x"
            )

    @pytest.mark.parametrize("field", sorted(SORTABLE_FIELDS))
    async def test_every_permitted_sort_field_works(
        self,
        field: str,
        search_engine: SearchEngine,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        results = await search_engine.search_by_property(
            organization_id,
            property_name="organization_id",
            value=str(organization_id),
            sort_by=field,
        )
        assert len(results.hits) == 5

    async def test_an_unpermitted_sort_field_names_the_permitted_ones(
        self, search_engine: SearchEngine, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(ValidationError, match="Sortable fields"):
            await search_engine.search_by_property(
                organization_id, property_name="name", value="x", sort_by="; DROP"
            )

    async def test_hits_are_enriched_with_their_metadata(
        self,
        search_engine: SearchEngine,
        twin_service: Any,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        await twin_service.set_state(
            organization_id, "app-1", criticality=0.9, owner_team="platform"
        )
        results = await search_engine.search(organization_id, "Billing")
        hit = next(one for one in results.hits if one.node.key == "app-1")
        assert hit.metadata is not None
        assert hit.metadata.owner_team == "platform"
        assert hit.as_dict()["metadata"]["criticality"] == 0.9

    async def test_metadata_search_filters_by_tag_and_team(
        self,
        search_engine: SearchEngine,
        twin_service: Any,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        await twin_service.set_state(
            organization_id, "app-1", tags=["billing", "tier-1"], owner_team="platform"
        )
        await twin_service.set_state(organization_id, "vm-1", tags=["infra"], owner_team="ops")

        by_tag = await search_engine.search_metadata(organization_id, tags=["billing"])
        assert [one.node_key for one in by_tag] == ["app-1"]

        by_team = await search_engine.search_metadata(organization_id, owner_team="ops")
        assert [one.node_key for one in by_team] == ["vm-1"]

    async def test_metadata_search_filters_by_criticality(
        self,
        search_engine: SearchEngine,
        twin_service: Any,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        await twin_service.set_state(organization_id, "app-1", criticality=0.9)
        await twin_service.set_state(organization_id, "vm-1", criticality=0.1)
        found = await search_engine.search_metadata(organization_id, min_criticality=0.5)
        assert [one.node_key for one in found] == ["app-1"]

    async def test_paging_reports_the_full_total(
        self,
        search_engine: SearchEngine,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        # The total is what tells a caller there is a second page; a
        # count of the current page would always say there is not.
        del seeded_graph
        page = await search_engine.search(organization_id, "vm", limit=1)
        assert len(page.hits) == 1
        assert page.total >= 2
        assert page.has_more is True

    async def test_the_results_dict_form_is_serialisable(
        self,
        search_engine: SearchEngine,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        results = await search_engine.search(organization_id, "Billing")
        payload = results.as_dict()
        assert payload["total"] >= 1
        assert isinstance(payload["hits"], list)


async def _engine_with_handler(
    graph: GraphRepository,
    db_session: Any,
    endpoints: SourceEndpoints,
    handler: Any,
    *,
    batch_size: int = 500,
    max_failures: int = 5,
) -> SynchronizationEngine:
    """A synchronization engine reading from a given stub transport."""
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return SynchronizationEngine(
        graph,
        GraphSyncJobRepository(db_session),
        GraphChangeHistoryRepository(db_session),
        GraphMetadataRepository(db_session),
        PlatformSourceClient(client, endpoints, service_token="test-token"),
        batch_size=batch_size,
        max_failures=max_failures,
    )
