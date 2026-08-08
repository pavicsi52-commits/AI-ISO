"""``GraphClient`` against a real Neo4j (docs/060 "KNOWLEDGE GRAPH QUERY").

A stub driver can confirm this service *builds* the Cypher it meant to.
Only a real database can confirm that Neo4j itself refuses a write
submitted through an explicit read transaction -- the guarantee the
Knowledge Graph Query tool kind rests on -- and that a traversal is
genuinely cut off at the configured record ceiling. Neither can be
asserted against a mock, so every test below runs against the real
``neo4j_driver``/``graph_client`` fixtures from ``tests/conftest.py``,
which skip for real if Neo4j is unreachable.

Neo4j has no SAVEPOINT equivalent, so every node this module creates is
tagged with a distinctive label (``AiAgentPlatformClientTest``) and a
per-test ``tag`` property, cleaned up with ``DETACH DELETE`` in the
``tagged_nodes`` fixture's own teardown -- never touching any other
test's data.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from neo4j import AsyncDriver
from shared_core.config.settings import Neo4jSettings
from shared_core.exceptions.dependency import DependencyError

from app.graph.client import GraphClient, QueryResult, create_neo4j_driver

_TEST_LABEL = "AiAgentPlatformClientTest"


@pytest_asyncio.fixture
async def tagged_nodes(neo4j_driver: AsyncDriver) -> AsyncIterator[str]:
    """A distinctive tag for this test's own nodes, purged afterwards."""
    tag = f"test-{uuid.uuid4()}"
    yield tag
    async with neo4j_driver.session(database="neo4j") as session:
        await session.run(
            f"MATCH (n:{_TEST_LABEL} {{tag: $tag}}) DETACH DELETE n",
            {"tag": tag},
        )


class TestCreateNeo4jDriver:
    def test_disabled_returns_none_without_touching_the_network(self) -> None:
        assert create_neo4j_driver(Neo4jSettings(_env_file=None), enabled=False) is None

    def test_building_never_raises_even_for_an_unreachable_host(self) -> None:
        # The driver connects lazily -- a bad host surfaces at query
        # time (see TestVerify below), never at construction.
        driver = create_neo4j_driver(
            Neo4jSettings(
                neo4j_host="127.0.0.1", neo4j_bolt_port=1, neo4j_password="x", _env_file=None
            )
        )
        assert driver is not None

    async def test_even_a_malformed_host_still_builds_a_driver_lazily(self) -> None:
        """``AsyncGraphDatabase.driver()`` never raises on a bad host.

        Verified directly against the real driver: hosts containing
        spaces, empty hosts, embedded schemes, and stray colons all
        build successfully, because construction does no resolution or
        connection at all. ``create_neo4j_driver``'s own try/except is
        therefore genuinely defensive rather than reachable from this
        field -- and a bad host surfaces at ``verify()``/query time
        instead, which is what ``TestVerify`` below covers.
        """
        driver = create_neo4j_driver(
            Neo4jSettings(neo4j_host="not a valid host", neo4j_password="x", _env_file=None)
        )
        assert driver is not None
        await driver.close()


class TestUnconfiguredClient:
    async def test_reports_itself_disabled(self) -> None:
        client = GraphClient(None, enabled=False)
        assert client.enabled is False

    async def test_enabled_flag_true_but_no_driver_is_still_unavailable(self) -> None:
        client = GraphClient(None, enabled=True)
        assert client.enabled is False

    async def test_verify_reports_false_without_a_driver(self) -> None:
        assert await GraphClient(None, enabled=False).verify() is False

    async def test_read_raises_not_configured(self) -> None:
        with pytest.raises(DependencyError, match="not configured"):
            await GraphClient(None, enabled=False).read("MATCH (n) RETURN n")

    async def test_write_raises_not_configured(self) -> None:
        with pytest.raises(DependencyError, match="not configured"):
            await GraphClient(None, enabled=False).write("RETURN 1")


class TestReadWrite:
    async def test_database_property(self, graph_client: GraphClient) -> None:
        assert graph_client.database == "neo4j"

    async def test_client_reports_itself_enabled(self, graph_client: GraphClient) -> None:
        assert graph_client.enabled is True

    async def test_write_then_read_round_trips(
        self, graph_client: GraphClient, tagged_nodes: str
    ) -> None:
        written = await graph_client.write(
            f"CREATE (n:{_TEST_LABEL} {{tag: $tag, name: $name}}) RETURN n.name AS name",
            {"tag": tagged_nodes, "name": "alpha"},
        )
        assert written.row_count == 1
        assert written.records[0]["name"] == "alpha"
        assert written.duration_ms >= 0

        read_back = await graph_client.read(
            f"MATCH (n:{_TEST_LABEL} {{tag: $tag}}) RETURN n.name AS name",
            {"tag": tagged_nodes},
        )
        assert read_back.row_count == 1
        assert read_back.scalar("name") == "alpha"
        assert read_back.truncated is False
        assert read_back.duration_ms >= 0

    async def test_read_rejects_a_write_clause(
        self, graph_client: GraphClient, tagged_nodes: str
    ) -> None:
        # This is the guarantee the Knowledge Graph Query tool kind
        # rests on: Neo4j itself refuses the write, not this service's
        # own say-so.
        with pytest.raises(DependencyError, match="Writing in read access mode not allowed"):
            await graph_client.read(
                f"CREATE (n:{_TEST_LABEL} {{tag: $tag}}) RETURN n",
                {"tag": tagged_nodes},
            )

        confirm = await graph_client.read(
            f"MATCH (n:{_TEST_LABEL} {{tag: $tag}}) RETURN count(n) AS total",
            {"tag": tagged_nodes},
        )
        assert confirm.scalar("total") == 0, "the refused write must not have happened"

    async def test_read_truncates_at_the_clients_own_record_ceiling(
        self, neo4j_driver: AsyncDriver, tagged_nodes: str
    ) -> None:
        await GraphClient(neo4j_driver, database="neo4j").write(
            f"UNWIND range(1, 5) AS i CREATE (n:{_TEST_LABEL} {{tag: $tag, i: i}})",
            {"tag": tagged_nodes},
        )
        small_ceiling_client = GraphClient(neo4j_driver, database="neo4j", max_records=2)

        result = await small_ceiling_client.read(
            f"MATCH (n:{_TEST_LABEL} {{tag: $tag}}) RETURN n.i AS i ORDER BY n.i",
            {"tag": tagged_nodes},
        )
        assert result.row_count == 2
        assert result.truncated is True

    async def test_read_max_records_override_beats_the_clients_own_ceiling(
        self, graph_client: GraphClient, tagged_nodes: str
    ) -> None:
        await graph_client.write(
            f"UNWIND range(1, 5) AS i CREATE (n:{_TEST_LABEL} {{tag: $tag, i: i}})",
            {"tag": tagged_nodes},
        )

        limited = await graph_client.read(
            f"MATCH (n:{_TEST_LABEL} {{tag: $tag}}) RETURN n.i AS i ORDER BY n.i",
            {"tag": tagged_nodes},
            max_records=3,
        )
        assert limited.row_count == 3
        assert limited.truncated is True

        full = await graph_client.read(
            f"MATCH (n:{_TEST_LABEL} {{tag: $tag}}) RETURN n.i AS i ORDER BY n.i",
            {"tag": tagged_nodes},
        )
        assert full.row_count == 5
        assert full.truncated is False

    async def test_a_malformed_read_statement_becomes_a_dependency_error(
        self, graph_client: GraphClient
    ) -> None:
        with pytest.raises(DependencyError, match="Graph query failed"):
            await graph_client.read("THIS IS NOT CYPHER")

    async def test_a_malformed_write_statement_becomes_a_dependency_error(
        self, graph_client: GraphClient
    ) -> None:
        with pytest.raises(DependencyError, match="Graph write failed"):
            await graph_client.write("THIS IS NOT CYPHER EITHER")

    async def test_write_with_no_parameters_defaults_to_empty(
        self, graph_client: GraphClient, tagged_nodes: str
    ) -> None:
        # No parameters at all -- the `parameters or {}` branch.
        result = await graph_client.write(f"CREATE (n:{_TEST_LABEL} {{tag: '{tagged_nodes}'}})")
        assert result.records == []


class TestVerify:
    async def test_a_reachable_graph_verifies(self, graph_client: GraphClient) -> None:
        assert await graph_client.verify() is True

    async def test_an_unreachable_driver_reports_false(self) -> None:
        # A real driver pointed at a real, dead port -- verify_connectivity
        # genuinely fails rather than being told to.
        dead_driver = create_neo4j_driver(
            Neo4jSettings(
                neo4j_host="127.0.0.1", neo4j_bolt_port=1, neo4j_password="x", _env_file=None
            )
        )
        assert dead_driver is not None
        client = GraphClient(dead_driver, database="neo4j")
        try:
            assert await client.verify() is False
        finally:
            await dead_driver.close()

    async def test_an_unreachable_driver_also_fails_a_real_query(self) -> None:
        dead_driver = create_neo4j_driver(
            Neo4jSettings(
                neo4j_host="127.0.0.1", neo4j_bolt_port=1, neo4j_password="x", _env_file=None
            )
        )
        assert dead_driver is not None
        client = GraphClient(dead_driver, database="neo4j", timeout_seconds=3.0)
        try:
            with pytest.raises(DependencyError, match="Graph query failed"):
                await client.read("RETURN 1")
        finally:
            await dead_driver.close()


class TestQueryResult:
    def test_scalar_defaults_when_there_are_no_records(self) -> None:
        empty = QueryResult()
        assert empty.scalar("missing", "fallback") == "fallback"
        assert empty.scalar("missing") is None
        assert empty.row_count == 0

    def test_scalar_reads_only_the_first_row(self) -> None:
        result = QueryResult(records=[{"total": 3}, {"total": 99}])
        assert result.scalar("total") == 3
        assert result.row_count == 2

    def test_defaults(self) -> None:
        result = QueryResult()
        assert result.records == []
        assert result.duration_ms == 0.0
        assert result.truncated is False
