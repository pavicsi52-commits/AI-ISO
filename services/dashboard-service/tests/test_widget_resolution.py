"""Widget resolution across every shape, and the paths that only fail.

The resolver is the one component every dashboard load runs through, so
its *failure* paths matter as much as its happy path: a source that
returns a 500, a topology widget on a deployment with no graph, an AI
widget with no assistant configured, and a query matching more rows
than the process should ever materialise all have to degrade into one
labelled tile rather than a broken dashboard.
"""

from __future__ import annotations

import uuid
from typing import Any, ClassVar

import httpx
import pytest
from shared_core.config.settings import Neo4jSettings
from sqlalchemy.ext.asyncio import AsyncSession

import app.topology.client as topology_client
from app.clients.platform import PlatformSourceClient, SourceEndpoints
from app.models.enums import DataSource, WidgetStatus, WidgetType
from app.topology.client import create_neo4j_driver
from app.topology.graph import TopologyReader
from app.widgets.resolver import ResolvedWidget, WidgetResolver
from tests.conftest import (
    INVENTORY_BASE_URL,
    SAMPLE_ROWS,
    FakeDriver,
    make_dashboard,
    make_widget,
    source_handler,
    topology_records,
)

ORG = uuid.UUID("44444444-4444-4444-4444-444444444444")


async def build_resolver(
    endpoints: SourceEndpoints,
    *,
    rows: list[dict[str, Any]] | None = None,
    status_code: int = 200,
    topology: TopologyReader | None = None,
    ai_client: Any | None = None,
    max_rows: int = 5_000,
) -> tuple[WidgetResolver, httpx.AsyncClient]:
    """A resolver over a stub transport, plus the client to close."""
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(source_handler(rows, status_code=status_code))
    )
    resolver = WidgetResolver(
        PlatformSourceClient(client, endpoints, caller_token="t", max_rows=max_rows),
        topology,
        ai_client,
        max_parallel=4,
        max_rows=max_rows,
    )
    return resolver, client


class TestWidgetShapes:
    """Every widget type reduces its rows into the right payload."""

    async def test_a_metric_card_reduces_to_one_number(
        self, db_session: AsyncSession, source_endpoints: SourceEndpoints
    ) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        widget = await make_widget(
            db_session,
            dashboard=dashboard,
            widget_type=WidgetType.METRIC_CARD,
            options={"metric": {"value_key": "cpu", "aggregate": "avg", "precision": 1}},
        )
        resolver, client = await build_resolver(source_endpoints)
        try:
            resolved = await resolver.resolve(widget, organization_id=ORG)
        finally:
            await client.aclose()

        assert resolved.status is WidgetStatus.OK
        assert resolved.payload["value"] == pytest.approx(54.9, abs=0.05)

    async def test_a_gauge_carries_its_bands_and_the_matched_one(
        self, db_session: AsyncSession, source_endpoints: SourceEndpoints
    ) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        widget = await make_widget(
            db_session,
            dashboard=dashboard,
            widget_type=WidgetType.GAUGE,
            options={
                "metric": {"value_key": "cpu", "aggregate": "max"},
                "thresholds": [
                    {"at": 50, "color": "#fa0", "label": "warning"},
                    {"at": 90, "color": "#f00", "label": "critical"},
                ],
            },
        )
        resolver, client = await build_resolver(source_endpoints)
        try:
            resolved = await resolver.resolve(widget, organization_id=ORG)
        finally:
            await client.aclose()

        assert resolved.payload["threshold"]["label"] == "critical"
        assert len(resolved.payload["bands"]) == 2

    async def test_a_chart_groups_into_a_series(
        self, db_session: AsyncSession, source_endpoints: SourceEndpoints
    ) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        widget = await make_widget(
            db_session,
            dashboard=dashboard,
            widget_type=WidgetType.BAR_CHART,
            options={
                "series": {"label_key": "env", "value_key": "cpu", "aggregate": "sum"},
                "stacked": True,
            },
        )
        resolver, client = await build_resolver(source_endpoints)
        try:
            resolved = await resolver.resolve(widget, organization_id=ORG)
        finally:
            await client.aclose()

        labels = {entry["label"] for entry in resolved.payload["series"]}
        assert labels == {"prod", "dev"}
        assert resolved.payload["stacked"] is True

    async def test_a_feed_truncates_visibly(
        self, db_session: AsyncSession, source_endpoints: SourceEndpoints
    ) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        widget = await make_widget(
            db_session,
            dashboard=dashboard,
            widget_type=WidgetType.ALERT_FEED,
            options={"limit": 2},
        )
        resolver, client = await build_resolver(source_endpoints)
        try:
            resolved = await resolver.resolve(widget, organization_id=ORG)
        finally:
            await client.aclose()

        assert len(resolved.payload["items"]) == 2
        assert resolved.payload["truncated"] is True

    async def test_a_table_truncates_visibly(
        self, db_session: AsyncSession, source_endpoints: SourceEndpoints
    ) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        widget = await make_widget(
            db_session,
            dashboard=dashboard,
            options={"columns": [{"key": "name", "label": "Host"}], "limit": 1},
        )
        resolver, client = await build_resolver(source_endpoints)
        try:
            resolved = await resolver.resolve(widget, organization_id=ORG)
        finally:
            await client.aclose()

        assert len(resolved.payload["rows"]) == 1
        assert resolved.payload["truncated"] is True

    async def test_an_unwired_widget_type_falls_through_to_raw_rows(
        self, db_session: AsyncSession, source_endpoints: SourceEndpoints
    ) -> None:
        # A newly added type nobody wired up must fall through visibly
        # rather than silently take another type's shape.
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        widget = await make_widget(
            db_session, dashboard=dashboard, widget_type=WidgetType.CUSTOM, options={}
        )
        resolver, client = await build_resolver(source_endpoints)
        try:
            resolved = await resolver.resolve(widget, organization_id=ORG)
        finally:
            await client.aclose()

        assert resolved.payload["rows"] == SAMPLE_ROWS

    async def test_a_markdown_widget_needs_no_data_source(
        self, db_session: AsyncSession, source_endpoints: SourceEndpoints
    ) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        widget = await make_widget(
            db_session,
            dashboard=dashboard,
            widget_type=WidgetType.MARKDOWN,
            data_source=DataSource.STATIC,
            query={"source": "static", "path": ""},
            options={"content": "# Runbook"},
        )
        resolver, client = await build_resolver(source_endpoints)
        try:
            resolved = await resolver.resolve(widget, organization_id=ORG)
        finally:
            await client.aclose()

        assert resolved.payload == {"content": "# Runbook"}
        assert resolved.row_count == 0

    async def test_a_static_query_yields_an_empty_widget(
        self, db_session: AsyncSession, source_endpoints: SourceEndpoints
    ) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        widget = await make_widget(
            db_session,
            dashboard=dashboard,
            widget_type=WidgetType.ALERT_FEED,
            query={"source": "static", "path": ""},
            options={"limit": 5},
        )
        resolver, client = await build_resolver(source_endpoints)
        try:
            resolved = await resolver.resolve(widget, organization_id=ORG)
        finally:
            await client.aclose()

        assert resolved.payload["items"] == []


class TestWidgetFailures:
    """Every failure becomes one labelled tile, never a dead dashboard."""

    async def test_an_unreachable_source_marks_only_its_own_widget(
        self, db_session: AsyncSession, source_endpoints: SourceEndpoints
    ) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        widget = await make_widget(db_session, dashboard=dashboard)
        resolver, client = await build_resolver(source_endpoints, status_code=503)
        try:
            resolved = await resolver.resolve(widget, organization_id=ORG)
        finally:
            await client.aclose()

        assert resolved.status is WidgetStatus.FAILED
        assert "503" in (resolved.error or "")
        assert resolved.duration_ms is not None

    async def test_a_malformed_stored_query_fails_the_widget_only(
        self, db_session: AsyncSession, source_endpoints: SourceEndpoints
    ) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        widget = await make_widget(
            db_session, dashboard=dashboard, query={"source": "nonsense", "path": "/x"}
        )
        resolver, client = await build_resolver(source_endpoints)
        try:
            resolved = await resolver.resolve(widget, organization_id=ORG)
        finally:
            await client.aclose()

        assert resolved.status is WidgetStatus.FAILED

    async def test_a_malformed_widget_filter_fails_the_widget_only(
        self, db_session: AsyncSession, source_endpoints: SourceEndpoints
    ) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        widget = await make_widget(
            db_session,
            dashboard=dashboard,
            filters=[{"field": "env", "operator": "nope", "value": "prod"}],
        )
        resolver, client = await build_resolver(source_endpoints)
        try:
            resolved = await resolver.resolve(widget, organization_id=ORG)
        finally:
            await client.aclose()

        assert resolved.status is WidgetStatus.FAILED
        assert "unknown operator" in (resolved.error or "")

    async def test_a_result_set_above_the_ceiling_is_refused(
        self, db_session: AsyncSession, source_endpoints: SourceEndpoints
    ) -> None:
        # A table widget pulling a million rows stalls the dashboard for
        # everyone on it; failing one widget clearly is strictly better.
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        widget = await make_widget(db_session, dashboard=dashboard)
        resolver, client = await build_resolver(
            source_endpoints, rows=[{"n": index} for index in range(10)], max_rows=3
        )
        try:
            resolved = await resolver.resolve(widget, organization_id=ORG)
        finally:
            await client.aclose()

        assert resolved.status is WidgetStatus.FAILED
        assert "ceiling" in (resolved.error or "")

    async def test_a_non_json_body_is_a_dependency_failure(
        self, db_session: AsyncSession, source_endpoints: SourceEndpoints
    ) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        widget = await make_widget(db_session, dashboard=dashboard)

        def _html(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="<html>proxy error</html>")

        client = httpx.AsyncClient(transport=httpx.MockTransport(_html))
        resolver = WidgetResolver(
            PlatformSourceClient(client, source_endpoints, caller_token="t"), None, None
        )
        try:
            resolved = await resolver.resolve(widget, organization_id=ORG)
        finally:
            await client.aclose()

        assert resolved.status is WidgetStatus.FAILED
        assert "non-JSON" in (resolved.error or "")

    async def test_a_transport_error_is_a_dependency_failure(
        self, db_session: AsyncSession, source_endpoints: SourceEndpoints
    ) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        widget = await make_widget(db_session, dashboard=dashboard)

        def _boom(_request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("no route to host")

        client = httpx.AsyncClient(transport=httpx.MockTransport(_boom))
        resolver = WidgetResolver(
            PlatformSourceClient(client, source_endpoints, caller_token="t"), None, None
        )
        try:
            resolved = await resolver.resolve(widget, organization_id=ORG)
        finally:
            await client.aclose()

        assert "unreachable" in (resolved.error or "")


class TestCustomApiWidgets:
    """``custom_api`` carries its own absolute URL, and is policed."""

    async def test_an_absolute_https_url_is_fetched(
        self, db_session: AsyncSession, source_endpoints: SourceEndpoints
    ) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        widget = await make_widget(
            db_session,
            dashboard=dashboard,
            data_source=DataSource.CUSTOM_API,
            query={"source": "custom_api", "path": "https://example.internal/data"},
        )
        resolver, client = await build_resolver(source_endpoints)
        try:
            resolved = await resolver.resolve(widget, organization_id=ORG)
        finally:
            await client.aclose()

        assert resolved.status is WidgetStatus.OK

    @pytest.mark.parametrize("path", ["file:///etc/passwd", "/relative/path", "ftp://host/x", ""])
    async def test_anything_that_is_not_an_absolute_http_url_is_refused(
        self, db_session: AsyncSession, source_endpoints: SourceEndpoints, path: str
    ) -> None:
        # A widget definition is user-authored content and must not be
        # able to point this service at arbitrary schemes.
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        widget = await make_widget(
            db_session,
            dashboard=dashboard,
            data_source=DataSource.CUSTOM_API,
            query={"source": "custom_api", "path": path},
        )
        resolver, client = await build_resolver(source_endpoints)
        try:
            resolved = await resolver.resolve(widget, organization_id=ORG)
        finally:
            await client.aclose()

        assert resolved.status is WidgetStatus.FAILED

    async def test_the_callers_token_is_forwarded_to_the_source(
        self, source_endpoints: SourceEndpoints
    ) -> None:
        # A dashboard must never be able to show data the viewing user
        # could not have fetched themselves.
        seen: list[str] = []

        def _capture(request: httpx.Request) -> httpx.Response:
            seen.append(request.headers.get("Authorization", ""))
            return httpx.Response(200, json={"data": []})

        async with httpx.AsyncClient(transport=httpx.MockTransport(_capture)) as client:
            await PlatformSourceClient(client, source_endpoints, caller_token="caller-token").fetch(
                DataSource.INVENTORY, "/inventory/assets"
            )

        assert seen == ["Bearer caller-token"]

    async def test_query_params_and_dashboard_parameters_are_merged(
        self, source_endpoints: SourceEndpoints
    ) -> None:
        seen: list[str] = []

        def _capture(request: httpx.Request) -> httpx.Response:
            seen.append(str(request.url))
            return httpx.Response(200, json={"data": []})

        async with httpx.AsyncClient(transport=httpx.MockTransport(_capture)) as client:
            await PlatformSourceClient(client, source_endpoints, caller_token="t").fetch(
                DataSource.INVENTORY, "/inventory/assets", params={"env": "prod"}
            )

        assert seen[0] == f"{INVENTORY_BASE_URL}/inventory/assets?env=prod"


class TestTopologyWidgets:
    """Topology widgets resolve through the graph, or fail cleanly."""

    async def test_a_topology_widget_renders_a_graph(
        self, db_session: AsyncSession, source_endpoints: SourceEndpoints
    ) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        widget = await make_widget(
            db_session,
            dashboard=dashboard,
            widget_type=WidgetType.TOPOLOGY_GRAPH,
            options={"topology": {"kind": "dependencies", "root_key": "asset_id", "depth": 2}},
        )
        reader = TopologyReader(FakeDriver(topology_records(2)))
        resolver, client = await build_resolver(source_endpoints, topology=reader)
        try:
            resolved = await resolver.resolve(
                widget, organization_id=ORG, parameters={"asset_id": "asset-1"}
            )
        finally:
            await client.aclose()

        assert resolved.status is WidgetStatus.OK
        assert resolved.payload["node_count"] == 3

    async def test_a_topology_widget_without_its_root_parameter_says_so(
        self, db_session: AsyncSession, source_endpoints: SourceEndpoints
    ) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        widget = await make_widget(
            db_session,
            dashboard=dashboard,
            widget_type=WidgetType.TOPOLOGY_GRAPH,
            options={"topology": {"kind": "neighbors", "root_key": "asset_id", "depth": 2}},
        )
        reader = TopologyReader(FakeDriver())
        resolver, client = await build_resolver(source_endpoints, topology=reader)
        try:
            resolved = await resolver.resolve(widget, organization_id=ORG)
        finally:
            await client.aclose()

        assert resolved.status is WidgetStatus.FAILED
        assert "'asset_id' parameter" in (resolved.error or "")

    async def test_no_graph_means_a_failed_widget_not_a_failed_dashboard(
        self, db_session: AsyncSession, source_endpoints: SourceEndpoints
    ) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        widget = await make_widget(
            db_session,
            dashboard=dashboard,
            widget_type=WidgetType.TOPOLOGY_GRAPH,
            options={"topology": {"kind": "neighbors", "depth": 2}},
        )
        resolver, client = await build_resolver(source_endpoints, topology=None)
        try:
            resolved = await resolver.resolve(widget, organization_id=ORG)
        finally:
            await client.aclose()

        assert resolved.status is WidgetStatus.FAILED
        assert "not configured" in (resolved.error or "")


class TestAiWidgets:
    """AI insight widgets go through Prompt 046, or report they cannot."""

    async def test_an_ai_widget_renders_its_summary(
        self, db_session: AsyncSession, source_endpoints: SourceEndpoints
    ) -> None:
        class Summary:
            text = "Fleet CPU is trending up."
            citations: ClassVar[list[str]] = ["doc-1"]

        class AiClient:
            enabled = True

            async def summarise(self, **_kwargs: Any) -> Summary:
                return Summary()

        dashboard = await make_dashboard(db_session, organization_id=ORG)
        widget = await make_widget(
            db_session,
            dashboard=dashboard,
            widget_type=WidgetType.AI_INSIGHT,
            options={"ai_prompt": "Summarise fleet health."},
        )
        resolver, client = await build_resolver(source_endpoints, ai_client=AiClient())
        try:
            resolved = await resolver.resolve(widget, organization_id=ORG)
        finally:
            await client.aclose()

        assert resolved.payload == {
            "text": "Fleet CPU is trending up.",
            "citations": ["doc-1"],
        }

    async def test_no_ai_client_means_a_failed_widget(
        self, db_session: AsyncSession, source_endpoints: SourceEndpoints
    ) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        widget = await make_widget(
            db_session,
            dashboard=dashboard,
            widget_type=WidgetType.AI_INSIGHT,
            options={"ai_prompt": "Summarise."},
        )
        resolver, client = await build_resolver(source_endpoints, ai_client=None)
        try:
            resolved = await resolver.resolve(widget, organization_id=ORG)
        finally:
            await client.aclose()

        assert resolved.status is WidgetStatus.FAILED
        assert "AI insights are not configured" in (resolved.error or "")


class TestResolveMany:
    """Concurrency is bounded and order-preserving."""

    async def test_widgets_come_back_in_the_order_they_were_given(
        self, db_session: AsyncSession, source_endpoints: SourceEndpoints
    ) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        widgets = [
            await make_widget(db_session, dashboard=dashboard, widget_key=f"w{index}")
            for index in range(5)
        ]
        resolver, client = await build_resolver(source_endpoints)
        try:
            resolved = await resolver.resolve_many(widgets, organization_id=ORG)
        finally:
            await client.aclose()

        assert [widget.widget_key for widget in resolved] == [
            f"w{index}" for index in range(5)
        ], "the caller already ordered the dashboard; it should not have to re-sort"

    async def test_resolving_nothing_is_cheap(self, source_endpoints: SourceEndpoints) -> None:
        resolver, client = await build_resolver(source_endpoints)
        try:
            assert await resolver.resolve_many([], organization_id=ORG) == []
        finally:
            await client.aclose()

    async def test_an_anonymous_resolver_labels_every_widget_unauthorized(
        self, db_session: AsyncSession
    ) -> None:
        # A share-link visitor has no credential, and this service holds
        # none of its own -- so structure, never data.
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        widget = await make_widget(db_session, dashboard=dashboard)
        resolver = WidgetResolver(None, None, None)

        resolved = await resolver.resolve(widget, organization_id=ORG)
        assert resolved.status is WidgetStatus.UNAUTHORIZED
        assert "Sign in" in (resolved.error or "")
        assert resolved.duration_ms is not None
        assert not resolved.failed, "unauthorized is not the same as failed"

    def test_a_resolved_widget_serialises_completely(self) -> None:
        resolved = ResolvedWidget(widget_key="hosts", widget_type=WidgetType.TABLE, title="Hosts")
        assert set(resolved.as_dict()) == {
            "widget_key",
            "widget_type",
            "title",
            "status",
            "payload",
            "error",
            "row_count",
            "duration_ms",
        }


class TestNeo4jDriverLifecycle:
    """Building the driver never fails startup."""

    def test_a_disabled_deployment_gets_no_driver(self) -> None:
        assert create_neo4j_driver(Neo4jSettings(_env_file=None), enabled=False) is None

    def test_a_configured_deployment_gets_a_driver(self) -> None:
        driver = create_neo4j_driver(Neo4jSettings(_env_file=None))
        assert driver is not None

    @pytest.mark.parametrize("host", ["", "a b", "::::"])
    def test_an_unusable_configuration_never_crashes_startup(self, host: str) -> None:
        # The neo4j driver connects lazily, so even a nonsense host is
        # accepted here and surfaces later as a failed readiness check
        # and a failed *widget*. What matters is that this call cannot
        # take the whole service down at boot -- every non-topology
        # dashboard must still serve.
        settings = Neo4jSettings(neo4j_host=host, _env_file=None)
        assert create_neo4j_driver(settings) is not None

    def test_a_raising_driver_factory_degrades_to_no_topology(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The guard that makes the statement above true, exercised
        # directly: should a future driver version validate eagerly,
        # this service reports "no topology" rather than failing to boot.
        def _boom(*_args: Any, **_kwargs: Any) -> Any:
            raise RuntimeError("unsupported URI scheme")

        monkeypatch.setattr(topology_client.AsyncGraphDatabase, "driver", _boom)
        assert create_neo4j_driver(Neo4jSettings(_env_file=None)) is None
