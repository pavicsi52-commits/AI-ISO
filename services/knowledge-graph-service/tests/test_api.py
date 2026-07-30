"""The HTTP contract, through the real application.

Driven with ``httpx.ASGITransport`` against an app started through its
actual lifespan: real PostgreSQL, real Redis, real RabbitMQ, real Neo4j,
real key loading, real middleware, real exception handlers. Only the
outbound source client is stubbed, so a sync has something deterministic
to read.

Two things are asserted here that no service-level test can reach:

- **Every route requires authentication.** A missing check is invisible
  from below -- the service layer never sees a caller -- and is the one
  defect in this file's subject that is unambiguously a vulnerability.
- **Status codes and error shapes.** The platform's conventions live in
  middleware and handlers, so 400 for a validation error and 503 with
  ``AIIOS-DEP-0001`` for a dependency failure are only observable over
  HTTP.
"""

from __future__ import annotations

import base64
import json
import uuid
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.graph.entities import NodeInput
from app.graph.repository import GraphRepository
from app.models.enums import (
    AnalyticsAlgorithm,
    GraphFormat,
    LifecycleState,
    NodeType,
    QueryKind,
    RelationshipType,
    SyncSource,
)
from tests.conftest import AuthHeadersFn

HTTP_OK = 200
HTTP_CREATED = 201
HTTP_BAD_REQUEST = 400
HTTP_UNAUTHORIZED = 401
HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409
HTTP_UNPROCESSABLE = 422

CALLER = uuid.UUID("11111111-1111-1111-1111-111111111111")

UNAUTHENTICATED_PATHS = frozenset({"/health", "/liveness", "/readiness", "/metrics"})
"""Routes that must answer without a token.

Health probes are called by Kubernetes, which has no bearer token, and
``/metrics`` by Prometheus. Everything else must refuse.
"""


def org(organization_id: uuid.UUID) -> dict[str, str]:
    """The organization query parameter every business route takes."""
    return {"organization_id": str(organization_id)}


def operations(app: FastAPI) -> list[tuple[str, str]]:
    """Every documented ``(method, path)`` this service exposes."""
    return sorted(
        (method.upper(), path)
        for path, methods in app.openapi()["paths"].items()
        for method in methods
        if method.lower() not in ("head", "options")
    )


class TestAuthentication:
    """No business route answers without a token."""

    def test_the_route_table_matches_the_specification(self, app: FastAPI) -> None:
        # Read from the OpenAPI document rather than by walking
        # app.routes: this FastAPI keeps an included router nested rather
        # than flattening its routes into the application, so an
        # isinstance sweep over app.routes finds only /metrics. The
        # generated document is also the contract a client actually sees.
        assert len(operations(app)) == 45

    def test_every_documented_path_is_under_graph_or_a_probe(self, app: FastAPI) -> None:
        for _method, path in operations(app):
            assert path.startswith(("/graph", "/health", "/liveness", "/readiness", "/metrics"))

    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("get", "/graph/nodes"),
            ("post", "/graph/nodes"),
            ("get", "/graph/nodes/app-1"),
            ("put", "/graph/nodes/app-1"),
            ("delete", "/graph/nodes/app-1"),
            ("get", "/graph/relationships"),
            ("post", "/graph/relationships"),
            ("get", "/graph/topology"),
            ("get", "/graph/path"),
            ("get", "/graph/dependencies"),
            ("get", "/graph/impact"),
            ("get", "/graph/blast-radius"),
            ("get", "/graph/analytics"),
            ("post", "/graph/analytics"),
            ("get", "/graph/statistics"),
            ("get", "/graph/search"),
            ("get", "/graph/twins"),
            ("get", "/graph/twins/app-1"),
            ("put", "/graph/twins/app-1"),
            ("post", "/graph/query"),
            ("post", "/graph/cypher"),
            ("get", "/graph/queries/saved"),
            ("post", "/graph/queries/saved"),
            ("get", "/graph/queries/history"),
            ("post", "/graph/sync"),
            ("get", "/graph/sync/history"),
            ("post", "/graph/import"),
            ("post", "/graph/export"),
            ("get", "/graph/snapshots"),
            ("post", "/graph/snapshots"),
            ("get", "/graph/versions"),
            ("get", "/graph/audit"),
            ("get", "/graph/audit/summary"),
            ("get", "/graph/history"),
        ],
    )
    async def test_every_business_route_refuses_an_anonymous_caller(
        self, method: str, path: str, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        # client.request, not client.get: httpx refuses a json body on a
        # GET, and the sweep has to cover both kinds in one table.
        response = await client.request(
            method.upper(),
            path,
            params=org(organization_id),
            **({"json": {}} if method in ("post", "put", "patch") else {}),
        )
        assert response.status_code == HTTP_UNAUTHORIZED, f"{method.upper()} {path} is unguarded"

    @pytest.mark.parametrize("path", sorted(UNAUTHENTICATED_PATHS))
    async def test_the_probes_answer_without_a_token(self, path: str, client: AsyncClient) -> None:
        # Kubernetes has no bearer token; a guarded liveness probe fails
        # the pod it is meant to be watching.
        assert (await client.get(path)).status_code == HTTP_OK

    async def test_a_malformed_token_is_refused(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        response = await client.get(
            "/graph/nodes",
            params=org(organization_id),
            headers={"Authorization": "Bearer not-a-jwt"},
        )
        assert response.status_code == HTTP_UNAUTHORIZED


class TestHealth:
    """What the orchestrator reads."""

    async def test_liveness_says_only_that_the_process_is_up(self, client: AsyncClient) -> None:
        # Deliberately dependency-free: a liveness probe that checked
        # Postgres would have Kubernetes restart a healthy process
        # because a database was briefly slow.
        assert (await client.get("/liveness")).status_code == HTTP_OK

    async def test_readiness_reports_each_dependency(self, client: AsyncClient) -> None:
        payload = (await client.get("/readiness")).json()
        named = {one["name"] for one in payload["data"]["checks"]}
        assert {"database", "cache", "graph"} <= named

    async def test_readiness_includes_the_graph(self, client: AsyncClient) -> None:
        # This service is useless without Neo4j, so it belongs in
        # readiness rather than being treated as optional.
        payload = (await client.get("/readiness")).json()
        graph_check = next(one for one in payload["data"]["checks"] if one["name"] == "graph")
        assert graph_check["status"] == "ok"

    async def test_health_reports_status_version_and_environment(self, client: AsyncClient) -> None:
        payload = (await client.get("/health")).json()
        assert payload["data"]["status"] == "healthy"
        assert payload["data"]["version"]
        assert payload["data"]["environment"]

    async def test_metrics_are_exposed_for_prometheus(self, client: AsyncClient) -> None:
        response = await client.get("/metrics")
        assert response.status_code == HTTP_OK
        assert "python_info" in response.text


class TestNodeRoutes:
    """Nodes over HTTP."""

    async def test_creating_a_node_returns_201(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del graph  # requested so the organization is purged afterwards
        response = await client.post(
            "/graph/nodes",
            params=org(organization_id),
            headers=auth_headers(CALLER),
            json={"key": "app-1", "node_type": NodeType.APPLICATION, "name": "Billing"},
        )
        assert response.status_code == HTTP_CREATED
        assert response.json()["data"]["key"] == "app-1"

    async def test_an_unknown_node_type_is_a_422(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        # Rejected by the schema before any Cypher is built, which is the
        # first of the two layers standing between a caller and a label
        # injected into a query.
        del graph
        response = await client.post(
            "/graph/nodes",
            params=org(organization_id),
            headers=auth_headers(CALLER),
            json={"key": "x", "node_type": "GraphNode) DETACH DELETE (n", "name": "x"},
        )
        # 400, not 422: the platform maps RequestValidationError to 400
        # so that every client-error response carries one shape.
        assert response.status_code == HTTP_BAD_REQUEST

    async def test_a_reserved_property_is_a_400(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        # A payload setting organization_id would move the node into
        # another tenant's graph.
        del graph
        response = await client.post(
            "/graph/nodes",
            params=org(organization_id),
            headers=auth_headers(CALLER),
            json={
                "key": "x",
                "node_type": NodeType.APPLICATION,
                "name": "x",
                "properties": {"organization_id": str(uuid.uuid4())},
            },
        )
        assert response.status_code == HTTP_BAD_REQUEST

    async def test_listing_nodes(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        response = await client.get(
            "/graph/nodes", params=org(organization_id), headers=auth_headers(CALLER)
        )
        assert response.status_code == HTTP_OK
        assert len(response.json()["data"]) == 5

    async def test_reading_one_node(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        response = await client.get(
            "/graph/nodes/app-1", params=org(organization_id), headers=auth_headers(CALLER)
        )
        assert response.status_code == HTTP_OK
        assert response.json()["data"]["name"] == "Billing"

    async def test_an_absent_node_is_a_404(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del graph
        response = await client.get(
            "/graph/nodes/ghost", params=org(organization_id), headers=auth_headers(CALLER)
        )
        assert response.status_code == HTTP_NOT_FOUND

    async def test_updating_a_node(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        response = await client.put(
            "/graph/nodes/app-1",
            params=org(organization_id),
            headers=auth_headers(CALLER),
            json={"key": "app-1", "node_type": NodeType.APPLICATION, "name": "Renamed"},
        )
        assert response.status_code == HTTP_OK
        assert response.json()["data"]["name"] == "Renamed"

    async def test_deleting_a_node(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        response = await client.delete(
            "/graph/nodes/vm-2", params=org(organization_id), headers=auth_headers(CALLER)
        )
        assert response.status_code == HTTP_OK

    async def test_deleting_an_absent_node_is_idempotent(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        # 200 with deleted=false rather than 404. Deliberate, and the same
        # choice delete_relationship makes: a delete retried after a
        # network timeout must not look like a new failure.
        del graph
        response = await client.delete(
            "/graph/nodes/ghost", params=org(organization_id), headers=auth_headers(CALLER)
        )
        assert response.status_code == HTTP_OK
        assert response.json()["data"]["deleted"] is False

    async def test_a_literal_collection_is_not_parsed_as_a_node_key(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        # FastAPI matches in registration order, so /graph/statistics
        # would otherwise resolve as a node whose key is the word
        # "statistics" -- a 404 on an endpoint that exists.
        del seeded_graph
        for path in ("/graph/statistics", "/graph/topology", "/graph/twins", "/graph/search"):
            response = await client.get(
                path,
                params={**org(organization_id), "root_key": "app-1", "q": "Billing"},
                headers=auth_headers(CALLER),
            )
            assert response.status_code != HTTP_NOT_FOUND, f"{path} was shadowed"


class TestRelationshipRoutes:
    """Relationships over HTTP."""

    async def test_creating_a_relationship(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        response = await client.post(
            "/graph/relationships",
            params=org(organization_id),
            headers=auth_headers(CALLER),
            json={
                "from_key": "app-1",
                "to_key": "host-1",
                "relationship_type": RelationshipType.DEPENDS_ON,
            },
        )
        assert response.status_code == HTTP_CREATED
        assert response.json()["data"]["relationship_key"] == "app-1|DEPENDS_ON|host-1"

    async def test_a_relationship_to_a_missing_node_is_a_404(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        response = await client.post(
            "/graph/relationships",
            params=org(organization_id),
            headers=auth_headers(CALLER),
            json={
                "from_key": "app-1",
                "to_key": "ghost",
                "relationship_type": RelationshipType.DEPENDS_ON,
            },
        )
        assert response.status_code == HTTP_NOT_FOUND

    async def test_a_self_loop_is_a_400(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        # A self-loop makes every dependency traversal cyclic and every
        # blast radius infinite.
        del seeded_graph
        response = await client.post(
            "/graph/relationships",
            params=org(organization_id),
            headers=auth_headers(CALLER),
            json={
                "from_key": "app-1",
                "to_key": "app-1",
                "relationship_type": RelationshipType.DEPENDS_ON,
            },
        )
        # 400 rather than 500: the model is built inside the handler, so a
        # bare ValueError would be wrapped by Pydantic into something
        # FastAPI has no handler for.
        assert response.status_code == HTTP_BAD_REQUEST

    async def test_listing_relationships(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        response = await client.get(
            "/graph/relationships", params=org(organization_id), headers=auth_headers(CALLER)
        )
        assert response.status_code == HTTP_OK
        # Each edge exactly once -- the undirected match used to double
        # every one of them.
        assert len(response.json()["data"]) == 5

    async def test_deleting_a_relationship_by_its_derived_key(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        response = await client.delete(
            "/graph/relationships/app-1|RUNS_ON|vm-1",
            params=org(organization_id),
            headers=auth_headers(CALLER),
        )
        assert response.status_code == HTTP_OK

    async def test_a_malformed_relationship_key_is_a_400(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del graph
        response = await client.delete(
            "/graph/relationships/not-a-composite-key",
            params=org(organization_id),
            headers=auth_headers(CALLER),
        )
        assert response.status_code == HTTP_BAD_REQUEST


class TestTraversalRoutes:
    """Topology, paths, and the analyses."""

    async def test_topology_includes_the_root(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        response = await client.get(
            "/graph/topology",
            params={**org(organization_id), "root_key": "app-1", "depth": 2},
            headers=auth_headers(CALLER),
        )
        assert response.status_code == HTTP_OK
        keys = {one["key"] for one in response.json()["data"]["nodes"]}
        assert "app-1" in keys

    async def test_every_edge_in_a_topology_response_names_a_node_it_contains(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        # The renderable-graph invariant, asserted at the boundary a
        # front end actually consumes.
        del seeded_graph
        payload = (
            await client.get(
                "/graph/topology",
                params={**org(organization_id), "root_key": "app-1", "depth": 3},
                headers=auth_headers(CALLER),
            )
        ).json()["data"]
        keys = {one["key"] for one in payload["nodes"]}
        for edge in payload["relationships"]:
            assert edge["from_key"] in keys
            assert edge["to_key"] in keys

    async def test_an_out_of_range_depth_is_rejected_by_the_schema(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        response = await client.get(
            "/graph/topology",
            params={**org(organization_id), "root_key": "app-1", "depth": 99},
            headers=auth_headers(CALLER),
        )
        assert response.status_code == HTTP_BAD_REQUEST

    async def test_the_shortest_path(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        response = await client.get(
            "/graph/path",
            params={**org(organization_id), "from_key": "app-1", "to_key": "host-1"},
            headers=auth_headers(CALLER),
        )
        assert response.status_code == HTTP_OK
        assert {one["key"] for one in response.json()["data"]["nodes"]} == {
            "app-1",
            "vm-1",
            "host-1",
        }

    @pytest.mark.parametrize(
        "path", ["/graph/dependencies", "/graph/impact", "/graph/blast-radius"]
    )
    async def test_each_analysis_answers(
        self,
        path: str,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        response = await client.get(
            path,
            params={**org(organization_id), "node_key": "host-1"},
            headers=auth_headers(CALLER),
        )
        assert response.status_code == HTTP_OK
        body = response.json()["data"]
        assert "risk_score" in body
        assert "severity" in body

    async def test_an_analysis_of_a_missing_node_is_a_404(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del graph
        response = await client.get(
            "/graph/impact",
            params={**org(organization_id), "node_key": "ghost"},
            headers=auth_headers(CALLER),
        )
        assert response.status_code == HTTP_NOT_FOUND


class TestAnalyticsRoutes:
    """The algorithm catalogue over HTTP."""

    async def test_the_default_analytics_summary(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        response = await client.get(
            "/graph/analytics",
            params={**org(organization_id), "algorithm": AnalyticsAlgorithm.DEGREE_CENTRALITY},
            headers=auth_headers(CALLER),
        )
        assert response.status_code == HTTP_OK

    @pytest.mark.parametrize("algorithm", list(AnalyticsAlgorithm))
    async def test_every_algorithm_is_reachable_over_http(
        self,
        algorithm: AnalyticsAlgorithm,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        response = await client.post(
            "/graph/analytics",
            params=org(organization_id),
            headers=auth_headers(CALLER),
            json={
                "algorithm": algorithm,
                "parameters": {
                    "from_key": "app-1",
                    "to_key": "host-1",
                    "root_key": "app-1",
                    "failed_keys": ["host-1"],
                },
            },
        )
        assert response.status_code == HTTP_OK
        assert response.json()["data"]["algorithm"] == str(algorithm)

    async def test_a_missing_required_parameter_is_a_400(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        response = await client.post(
            "/graph/analytics",
            params=org(organization_id),
            headers=auth_headers(CALLER),
            json={"algorithm": AnalyticsAlgorithm.SHORTEST_PATH, "parameters": {}},
        )
        assert response.status_code == HTTP_BAD_REQUEST

    async def test_statistics_are_serialisable(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        response = await client.get(
            "/graph/statistics", params=org(organization_id), headers=auth_headers(CALLER)
        )
        assert response.status_code == HTTP_OK
        body = response.json()["data"]
        assert body["node_count"] == 5
        assert json.dumps(body)


class TestQueryRoutes:
    """The security boundary, over HTTP."""

    async def test_a_builtin_query_runs(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        response = await client.post(
            "/graph/query",
            params=org(organization_id),
            headers=auth_headers(CALLER),
            json={"kind": QueryKind.SERVICE_DEPENDENCY, "parameters": {"root_key": "app-1"}},
        )
        assert response.status_code == HTTP_OK
        assert response.json()["data"]["row_count"] >= 1

    async def test_read_only_cypher_runs(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        response = await client.post(
            "/graph/cypher",
            params=org(organization_id),
            headers=auth_headers(CALLER),
            json={
                "cypher": (
                    "MATCH (n:GraphNode {organization_id: $organization_id}) "
                    "RETURN n.key AS key ORDER BY key LIMIT $limit"
                )
            },
        )
        assert response.status_code == HTTP_OK
        assert response.json()["data"]["row_count"] == 5

    @pytest.mark.parametrize(
        "statement",
        [
            "MATCH (n:GraphNode) DETACH DELETE n",
            "CREATE (n:GraphNode {key: 'x'}) RETURN n",
            "MATCH (n:GraphNode) SET n.name = 'x' RETURN n",
            "MATCH (n:GraphNode) REMOVE n.name RETURN n",
            "MERGE (n:GraphNode {key: 'x'}) RETURN n",
            "CALL dbms.security.createUser('x', 'y')",
            "LOAD CSV FROM 'file:///etc/passwd' AS row RETURN row",
            "MATCH (n:GraphNode) RETURN n LIMIT 5",
            "MATCH (a)-[r*1..50]-(b) RETURN a, b LIMIT $limit",
        ],
    )
    async def test_a_dangerous_statement_is_refused_over_http(
        self,
        statement: str,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        # Writes, procedure calls, file reads, bare literals, and
        # unbounded variable-length patterns. All 400, with the reason
        # named -- a 500 from the driver would tell the caller nothing
        # and leave nothing auditable.
        del graph
        response = await client.post(
            "/graph/cypher",
            params=org(organization_id),
            headers=auth_headers(CALLER),
            json={"cypher": statement},
        )
        assert response.status_code == HTTP_BAD_REQUEST, statement

    async def test_a_refused_statement_leaves_an_audit_entry(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        # The entry the trail exists for: a probe changes no state, so a
        # trail of successes alone would show nothing where the
        # interesting event was.
        del graph
        await client.post(
            "/graph/cypher",
            params=org(organization_id),
            headers=auth_headers(CALLER),
            json={"cypher": "MATCH (n) DETACH DELETE n"},
        )
        audit = await client.get(
            "/graph/audit", params=org(organization_id), headers=auth_headers(CALLER)
        )
        entries = audit.json()["data"]
        assert any(one["outcome"] == "denied" for one in entries)

    async def test_a_saved_query_round_trips_over_http(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        created = await client.post(
            "/graph/queries/saved",
            params=org(organization_id),
            headers=auth_headers(CALLER),
            json={
                "slug": "by-type",
                "name": "Nodes by type",
                "cypher": (
                    "MATCH (n:GraphNode {organization_id: $organization_id}) "
                    "WHERE n.node_type = $node_type RETURN n.key AS key LIMIT $limit"
                ),
                "parameter_schema": {"node_type": "string"},
            },
        )
        assert created.status_code == HTTP_CREATED

        run = await client.post(
            "/graph/queries/saved/by-type/run",
            params=org(organization_id),
            headers=auth_headers(CALLER),
            json={"parameters": {"node_type": "Database"}},
        )
        assert run.status_code == HTTP_OK
        assert run.json()["data"]["row_count"] == 1

        listed = await client.get(
            "/graph/queries/saved", params=org(organization_id), headers=auth_headers(CALLER)
        )
        assert [one["slug"] for one in listed.json()["data"]] == ["by-type"]

        removed = await client.delete(
            "/graph/queries/saved/by-type",
            params=org(organization_id),
            headers=auth_headers(CALLER),
        )
        assert removed.status_code == HTTP_OK

    async def test_a_write_cannot_be_saved(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del graph
        response = await client.post(
            "/graph/queries/saved",
            params=org(organization_id),
            headers=auth_headers(CALLER),
            json={"slug": "bad", "name": "Bad", "cypher": "MATCH (n) DETACH DELETE n"},
        )
        assert response.status_code == HTTP_BAD_REQUEST

    async def test_a_duplicate_slug_is_a_409(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del graph
        body = {
            "slug": "dupe",
            "name": "Dupe",
            "cypher": "MATCH (n:GraphNode) RETURN n LIMIT $limit",
        }
        first = await client.post(
            "/graph/queries/saved",
            params=org(organization_id),
            headers=auth_headers(CALLER),
            json=body,
        )
        assert first.status_code == HTTP_CREATED
        second = await client.post(
            "/graph/queries/saved",
            params=org(organization_id),
            headers=auth_headers(CALLER),
            json=body,
        )
        assert second.status_code == HTTP_CONFLICT

    async def test_running_an_unknown_saved_query_is_a_404(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del graph
        response = await client.post(
            "/graph/queries/saved/nope/run",
            params=org(organization_id),
            headers=auth_headers(CALLER),
            json={},
        )
        assert response.status_code == HTTP_NOT_FOUND

    async def test_query_history_records_what_ran(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        await client.post(
            "/graph/query",
            params=org(organization_id),
            headers=auth_headers(CALLER),
            json={"kind": QueryKind.OWNERSHIP},
        )
        history = await client.get(
            "/graph/queries/history", params=org(organization_id), headers=auth_headers(CALLER)
        )
        assert history.status_code == HTTP_OK
        assert len(history.json()["data"]) == 1


class TestSearchRoutes:
    """Search over HTTP."""

    async def test_searching_by_text(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        response = await client.get(
            "/graph/search",
            params={**org(organization_id), "q": "Billing"},
            headers=auth_headers(CALLER),
        )
        assert response.status_code == HTTP_OK
        assert response.json()["data"]["total"] >= 1

    async def test_an_empty_query_is_rejected(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del graph
        response = await client.get(
            "/graph/search",
            params={**org(organization_id), "q": "   "},
            headers=auth_headers(CALLER),
        )
        assert response.status_code == HTTP_BAD_REQUEST


class TestTwinRoutes:
    """Digital twins over HTTP."""

    async def test_reading_a_twin(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        response = await client.get(
            "/graph/twins/app-1", params=org(organization_id), headers=auth_headers(CALLER)
        )
        assert response.status_code == HTTP_OK
        assert response.json()["data"]["twin_type"] == "application"

    async def test_recording_twin_state(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        response = await client.put(
            "/graph/twins/app-1",
            params=org(organization_id),
            headers=auth_headers(CALLER),
            json={
                "lifecycle_state": LifecycleState.ACTIVE,
                "criticality": 0.9,
                "owner_team": "platform",
                "tags": ["billing"],
            },
        )
        assert response.status_code == HTTP_OK

        listed = await client.get(
            "/graph/twins", params=org(organization_id), headers=auth_headers(CALLER)
        )
        assert [one["node_key"] for one in listed.json()["data"]] == ["app-1"]

    async def test_state_for_a_missing_node_is_a_404(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del graph
        response = await client.put(
            "/graph/twins/ghost",
            params=org(organization_id),
            headers=auth_headers(CALLER),
            json={"criticality": 0.5},
        )
        assert response.status_code == HTTP_NOT_FOUND

    async def test_criticality_outside_the_unit_interval_is_rejected(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        response = await client.put(
            "/graph/twins/app-1",
            params=org(organization_id),
            headers=auth_headers(CALLER),
            json={"criticality": 5.0},
        )
        assert response.status_code == HTTP_BAD_REQUEST


class TestSyncRoutes:
    """Synchronization over HTTP."""

    async def test_triggering_a_sync(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del graph
        response = await client.post(
            "/graph/sync",
            params=org(organization_id),
            headers=auth_headers(CALLER),
            json={"sources": [SyncSource.INVENTORY]},
        )
        assert response.status_code == HTTP_OK
        assert response.json()["data"]["succeeded"] == 1

    async def test_sync_history(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del graph
        await client.post(
            "/graph/sync",
            params=org(organization_id),
            headers=auth_headers(CALLER),
            json={"sources": [SyncSource.INVENTORY]},
        )
        response = await client.get(
            "/graph/sync/history", params=org(organization_id), headers=auth_headers(CALLER)
        )
        assert response.status_code == HTTP_OK
        assert len(response.json()["data"]) == 1

    async def test_resetting_a_source(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del graph
        await client.post(
            "/graph/sync",
            params=org(organization_id),
            headers=auth_headers(CALLER),
            json={"sources": [SyncSource.INVENTORY]},
        )
        response = await client.post(
            f"/graph/sync/{SyncSource.INVENTORY}/reset",
            params=org(organization_id),
            headers=auth_headers(CALLER),
        )
        assert response.status_code == HTTP_OK


class TestImportExportRoutes:
    """Bulk I/O over HTTP."""

    async def test_an_import_writes_nodes(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        payload = json.dumps(
            {
                "nodes": [
                    {"key": "imported-1", "node_type": "Application", "name": "Imported"},
                ],
                "relationships": [],
            }
        ).encode("utf-8")
        response = await client.post(
            "/graph/import",
            params=org(organization_id),
            headers=auth_headers(CALLER),
            json={
                "filename": "graph.json",
                "graph_format": GraphFormat.JSON,
                "content": base64.b64encode(payload).decode("ascii"),
            },
        )
        assert response.status_code in (HTTP_OK, HTTP_CREATED)
        assert await graph.get_node(organization_id, "imported-1") is not None

    async def test_a_dry_run_writes_nothing(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        # The point of a dry run: validate a file someone is about to
        # apply to a live graph without applying it.
        payload = json.dumps(
            {"nodes": [{"key": "dry-1", "node_type": "Application", "name": "Dry"}]}
        ).encode("utf-8")
        await client.post(
            "/graph/import",
            params=org(organization_id),
            headers=auth_headers(CALLER),
            json={
                "filename": "graph.json",
                "graph_format": GraphFormat.JSON,
                "content": base64.b64encode(payload).decode("ascii"),
                "dry_run": True,
            },
        )
        assert await graph.get_node(organization_id, "dry-1") is None

    async def test_a_malformed_payload_is_a_400(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del graph
        result = await client.post(
            "/graph/import",
            params=org(organization_id),
            headers=auth_headers(CALLER),
            json={
                "filename": "graph.json",
                "graph_format": GraphFormat.JSON,
                "content": base64.b64encode(b"{not json").decode("ascii"),
            },
        )
        assert result.status_code == HTTP_BAD_REQUEST

    @pytest.mark.parametrize("graph_format", list(GraphFormat))
    async def test_an_export_can_be_downloaded_in_every_format(
        self,
        graph_format: GraphFormat,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        created = await client.post(
            "/graph/export",
            params=org(organization_id),
            headers=auth_headers(CALLER),
            json={"graph_format": graph_format},
        )
        assert created.status_code in (HTTP_OK, HTTP_CREATED)
        export_id = created.json()["data"]["id"]

        downloaded = await client.get(
            f"/graph/export/{export_id}/download", headers=auth_headers(CALLER)
        )
        assert downloaded.status_code == HTTP_OK
        assert downloaded.content

    async def test_downloading_an_unknown_export_is_a_404(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        response = await client.get(
            f"/graph/export/{uuid.uuid4()}/download", headers=auth_headers(CALLER)
        )
        assert response.status_code == HTTP_NOT_FOUND


class TestSnapshotRoutes:
    """Snapshots and versions over HTTP."""

    async def test_capture_restore_and_diff(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        seeded_graph: GraphRepository,
        graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        created = await client.post(
            "/graph/snapshots",
            params=org(organization_id),
            headers=auth_headers(CALLER),
            json={"label": "nightly"},
        )
        assert created.status_code in (HTTP_OK, HTTP_CREATED)
        body = created.json()["data"]
        assert body["node_count"] == 5
        snapshot_id = body["id"]

        await graph.delete_node(organization_id, "vm-2")
        diff = await client.get(
            f"/graph/snapshots/{snapshot_id}/diff",
            params=org(organization_id),
            headers=auth_headers(CALLER),
        )
        assert diff.status_code == HTTP_OK
        assert diff.json()["data"]["removed_nodes"] == ["vm-2"]

        restored = await client.post(
            f"/graph/snapshots/{snapshot_id}/restore",
            params=org(organization_id),
            headers=auth_headers(CALLER),
        )
        assert restored.status_code == HTTP_OK
        assert await graph.count_nodes(organization_id) == 5

    async def test_listing_snapshots_and_versions(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        await client.post(
            "/graph/snapshots",
            params=org(organization_id),
            headers=auth_headers(CALLER),
            json={"label": "one"},
        )
        snapshots = await client.get(
            "/graph/snapshots", params=org(organization_id), headers=auth_headers(CALLER)
        )
        assert len(snapshots.json()["data"]) == 1

        versions = await client.get(
            "/graph/versions", params=org(organization_id), headers=auth_headers(CALLER)
        )
        assert versions.status_code == HTTP_OK

    async def test_restoring_an_unknown_snapshot_is_a_404(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del graph
        response = await client.post(
            f"/graph/snapshots/{uuid.uuid4()}/restore",
            params=org(organization_id),
            headers=auth_headers(CALLER),
        )
        assert response.status_code == HTTP_NOT_FOUND


class TestAuditRoutes:
    """The trail over HTTP."""

    async def test_a_write_is_audited(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del graph
        await client.post(
            "/graph/nodes",
            params=org(organization_id),
            headers=auth_headers(CALLER),
            json={"key": "app-1", "node_type": NodeType.APPLICATION, "name": "Billing"},
        )
        audit = await client.get(
            "/graph/audit", params=org(organization_id), headers=auth_headers(CALLER)
        )
        assert audit.status_code == HTTP_OK
        assert [one["entity_key"] for one in audit.json()["data"]] == ["app-1"]

    async def test_the_audit_summary(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del graph
        await client.post(
            "/graph/nodes",
            params=org(organization_id),
            headers=auth_headers(CALLER),
            json={"key": "app-1", "node_type": NodeType.APPLICATION, "name": "Billing"},
        )
        summary = await client.get(
            "/graph/audit/summary", params=org(organization_id), headers=auth_headers(CALLER)
        )
        assert summary.status_code == HTTP_OK
        assert summary.json()["data"]["total"] == 1

    async def test_change_history(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del graph
        await client.post(
            "/graph/nodes",
            params=org(organization_id),
            headers=auth_headers(CALLER),
            json={"key": "app-1", "node_type": NodeType.APPLICATION, "name": "Billing"},
        )
        history = await client.get(
            "/graph/history", params=org(organization_id), headers=auth_headers(CALLER)
        )
        assert history.status_code == HTTP_OK
        assert len(history.json()["data"]) == 1


class TestResponseEnvelope:
    """The platform's shared response shape."""

    async def test_a_success_carries_message_data_and_meta(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        payload = (
            await client.get(
                "/graph/nodes", params=org(organization_id), headers=auth_headers(CALLER)
            )
        ).json()
        assert payload["success"] is True
        assert payload["message"]
        assert "data" in payload
        assert "meta" in payload

    async def test_an_error_carries_a_platform_error_code(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del graph
        payload = (
            await client.get(
                "/graph/nodes/ghost", params=org(organization_id), headers=auth_headers(CALLER)
            )
        ).json()
        assert payload["success"] is False
        assert payload["error"]["code"].startswith("AIIOS-")

    async def test_no_route_is_versioned_in_its_own_path(self, app: FastAPI) -> None:
        # The gateway owns versioning; a service that prefixed /api/v1
        # itself would be reachable at /api/v1/api/v1/... through it.
        for _method, path in operations(app):
            assert not path.startswith("/api/")

    async def test_security_headers_are_applied(self, client: AsyncClient) -> None:
        response = await client.get("/health")
        names = {name.lower() for name in response.headers}
        assert "x-content-type-options" in names

    async def test_a_request_is_logged_with_its_latency(
        self, client: AsyncClient, caplog: Any
    ) -> None:
        # The timing middleware logs rather than adding a header, so the
        # latency lands in the structured log a dashboard reads instead of
        # in a response a caller could not act on anyway.
        with caplog.at_level("INFO", logger="app.request"):
            await client.get("/health")
        assert any("request completed" in record.message for record in caplog.records)


class TestTenantScoping:
    """One organization never reads another's graph over HTTP."""

    async def test_a_different_organization_sees_an_empty_graph(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        seeded_graph: GraphRepository,
        graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        other = uuid.uuid4()
        try:
            response = await client.get(
                "/graph/nodes", params=org(other), headers=auth_headers(CALLER)
            )
            assert response.json()["data"] == []
        finally:
            await graph.purge_organization(other)

    async def test_a_node_in_another_organization_is_a_404(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        seeded_graph: GraphRepository,
        graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        other = uuid.uuid4()
        try:
            response = await client.get(
                "/graph/nodes/app-1", params=org(other), headers=auth_headers(CALLER)
            )
            assert response.status_code == HTTP_NOT_FOUND
        finally:
            await graph.purge_organization(other)


async def _seed_one(graph: GraphRepository, organization_id: uuid.UUID, key: str) -> Any:
    """Write one node, for tests that need exactly one."""
    return await graph.upsert_node(
        organization_id, NodeInput(key=key, node_type=NodeType.APPLICATION, name=key)
    )
