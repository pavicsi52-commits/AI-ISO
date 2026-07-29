"""The two live transports and the topology route, driven end to end.

These need a synchronous ``TestClient``: ``httpx.ASGITransport`` buffers
a response body to completion, so requesting an endpoint that streams
forever would hang the suite rather than exercise it. Starlette's
``TestClient`` runs the app on its own loop and hands back a real
socket, which is what makes "does a WebSocket actually deliver a frame?"
answerable at all.

Because that client owns its own event loop, these tests use their own
app instance rather than the async ``app`` fixture, and read committed
data rather than SAVEPOINT-isolated data -- so each one creates its
rows through a real committed transaction and removes them afterwards.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from shared_core.database.engine import create_engine
from shared_core.security.jwt import encode_token
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api.analytics import stream as stream_route
from app.core.factory import create_app
from app.models.enums import StreamEventKind
from app.realtime.hub import DashboardHub
from app.repositories.dashboard import DashboardRepository
from app.repositories.dashboard_history import DashboardHistoryRepository
from app.repositories.dashboard_layout import DashboardLayoutRepository
from app.repositories.dashboard_view import DashboardViewRepository
from app.repositories.dashboard_widget import DashboardWidgetRepository
from app.services.dashboard import DashboardService
from app.services.streaming import StreamingService
from app.topology.graph import TopologyReader
from app.widgets.resolver import WidgetResolver
from tests.conftest import (
    FakeDriver,
    RecordingPublisher,
    make_dashboard,
    make_widget,
    postgres_test_settings,
    topology_records,
)

ORG = uuid.UUID("55555555-5555-5555-5555-555555555555")

HTTP_OK = 200
POLICY_VIOLATION = 1008
TRY_AGAIN_LATER = 1013


_INSERT_DASHBOARD = text(
    "INSERT INTO dashboards "
    "(id, organization_id, slug, name, dashboard_type, visibility, "
    " default_filters, refresh_seconds, layout_revision, enabled, "
    " created_at, updated_at, is_active, version) "
    "VALUES (:id, :org, :slug, :name, 'infrastructure', 'organization', "
    " '[]', 0, 1, true, now(), now(), true, 1)"
)


def _run(statement: Any, parameters: dict[str, Any]) -> None:
    """Execute one statement on a throwaway engine and loop.

    A fresh engine per call, because an ``AsyncEngine`` binds to the
    loop it was created on and these tests deliberately run on their
    own -- reusing the suite's ``pg_engine`` here raises "attached to a
    different loop".
    """

    async def _execute() -> None:
        engine: AsyncEngine = create_engine(postgres_test_settings())
        try:
            async with engine.begin() as conn:
                await conn.execute(statement, parameters)
        finally:
            await engine.dispose()

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_execute())
    finally:
        loop.close()


@pytest.fixture
def committed_dashboard() -> Iterator[uuid.UUID]:
    """One dashboard genuinely committed, then removed afterwards.

    The streaming transports run on their own event loop, so they cannot
    see rows held open in another test's SAVEPOINT.
    """
    dashboard_id = uuid.uuid4()
    try:
        _run(
            _INSERT_DASHBOARD,
            {
                "id": dashboard_id,
                "org": ORG,
                "slug": f"t{dashboard_id.hex[:8]}",
                "name": "Transport",
            },
        )
    except OSError as exc:  # pragma: no cover -- infrastructure absent
        pytest.skip(f"PostgreSQL is not reachable: {exc}")

    yield dashboard_id

    _run(text("DELETE FROM dashboards WHERE id = :id"), {"id": dashboard_id})


@pytest.fixture
def sync_app(jwt_keypair: tuple[str, str]) -> Iterator[FastAPI]:
    """A real app instance driven by a synchronous ``TestClient``."""
    del jwt_keypair  # the app loads the same key from its configured path
    application = create_app()
    yield application


def token(user_id: uuid.UUID, jwt_keypair: tuple[str, str]) -> str:
    """A valid access token for *user_id*."""
    private_key, _public = jwt_keypair
    return encode_token({"sub": str(user_id)}, private_key=private_key)


class TestWebSocketTransport:
    """The WebSocket transport, over a real socket."""

    def test_a_valid_token_receives_presence_then_heartbeats(
        self,
        sync_app: FastAPI,
        jwt_keypair: tuple[str, str],
        committed_dashboard: uuid.UUID,
    ) -> None:
        access = token(uuid.uuid4(), jwt_keypair)
        with TestClient(sync_app) as client:
            sync_app.state.service_settings.stream_heartbeat_seconds = 1
            with client.websocket_connect(
                f"/dashboards/{committed_dashboard}/ws?token={access}"
            ) as socket:
                first = json.loads(socket.receive_text())
                assert first["kind"] == StreamEventKind.PRESENCE
                assert first["payload"]["watchers"], "the connecting client is present"

                second = json.loads(socket.receive_text())
                assert second["kind"] == StreamEventKind.HEARTBEAT, (
                    "an idle socket is indistinguishable from a dead one without "
                    "a heartbeat, and proxies close silent connections"
                )

    def test_a_published_update_reaches_a_connected_socket(
        self,
        sync_app: FastAPI,
        jwt_keypair: tuple[str, str],
        committed_dashboard: uuid.UUID,
    ) -> None:
        access = token(uuid.uuid4(), jwt_keypair)
        with (
            TestClient(sync_app) as client,
            client.websocket_connect(
                f"/dashboards/{committed_dashboard}/ws?token={access}"
            ) as socket,
        ):
            assert json.loads(socket.receive_text())["kind"] == StreamEventKind.PRESENCE

            response = client.post(
                f"/dashboards/{committed_dashboard}/refresh",
                headers={"Authorization": f"Bearer {access}"},
            )
            assert response.json()["data"]["delivered"] == 1

            frame = json.loads(socket.receive_text())
            assert frame["kind"] == StreamEventKind.UPDATE
            assert frame["payload"]["action"] == "reload"
            assert "widgets" not in frame["payload"], (
                "a broadcast reaches every watcher at once, and those are "
                "different people with different rights"
            )

    def test_no_token_is_closed_with_policy_violation(self, sync_app: FastAPI) -> None:
        with (
            TestClient(sync_app) as client,
            pytest.raises(WebSocketDisconnect) as caught,
            client.websocket_connect(f"/dashboards/{uuid.uuid4()}/ws"),
        ):
            pass
        assert caught.value.code == POLICY_VIOLATION

    def test_a_forged_token_is_closed_with_policy_violation(self, sync_app: FastAPI) -> None:
        with (
            TestClient(sync_app) as client,
            pytest.raises(WebSocketDisconnect) as caught,
            client.websocket_connect(f"/dashboards/{uuid.uuid4()}/ws?token=forged"),
        ):
            pass
        assert caught.value.code == POLICY_VIOLATION

    def test_the_subscriber_ceiling_refuses_the_handshake(
        self, sync_app: FastAPI, jwt_keypair: tuple[str, str]
    ) -> None:
        # Refusing a connection is far better than accepting one the
        # process cannot serve.
        access = token(uuid.uuid4(), jwt_keypair)
        with TestClient(sync_app) as client:
            sync_app.state.hub._max_subscribers = 0
            with (
                pytest.raises(WebSocketDisconnect) as caught,
                client.websocket_connect(f"/dashboards/{uuid.uuid4()}/ws?token={access}"),
            ):
                pass
            assert caught.value.code == TRY_AGAIN_LATER

    def test_disconnecting_removes_the_subscriber(
        self,
        sync_app: FastAPI,
        jwt_keypair: tuple[str, str],
        committed_dashboard: uuid.UUID,
    ) -> None:
        access = token(uuid.uuid4(), jwt_keypair)
        with TestClient(sync_app) as client:
            with client.websocket_connect(
                f"/dashboards/{committed_dashboard}/ws?token={access}"
            ) as socket:
                socket.receive_text()
                assert sync_app.state.hub.count_for(committed_dashboard) == 1
            # Give the server task its turn to run the finally block.
            client.get("/health")
        assert sync_app.state.hub.count_for(committed_dashboard) == 0


class TestServerSentEventTransport:
    """The SSE route body, driven directly.

    Deliberately **not** through a test client. Both
    ``httpx.ASGITransport`` and Starlette's ``TestClient`` want a
    response body that ends, and an SSE stream is endless by
    construction -- driving it through either hangs the suite instead of
    testing it. Calling the route function and consuming its own
    generator exercises the same code with none of that.
    """

    async def test_the_route_yields_a_snapshot_then_live_frames(
        self, db_session: AsyncSession, resolver: WidgetResolver, publisher: RecordingPublisher
    ) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        await make_widget(db_session, dashboard=dashboard)
        hub = DashboardHub()
        streaming = StreamingService(
            hub,
            DashboardService(
                DashboardRepository(db_session),
                DashboardWidgetRepository(db_session),
                DashboardLayoutRepository(db_session),
                DashboardHistoryRepository(db_session),
                DashboardViewRepository(db_session),
                resolver,
                publish_event=publisher,
            ),
        )

        class _Settings:
            stream_heartbeat_seconds = 1

        class _State:
            service_settings = _Settings()

        class _App:
            state = _State()

        class _Request:
            app = _App()

        response = await stream_route(
            _Request(),  # type: ignore[arg-type]
            dashboard.id,
            streaming,
            uuid.uuid4(),
        )
        assert response.media_type == "text/event-stream"
        assert response.headers["cache-control"] == "no-cache"
        assert response.headers["x-accel-buffering"] == "no", (
            "without this an nginx in front would buffer the stream and "
            "deliver nothing until the connection closed"
        )
        assert hub.count_for(dashboard.id) == 1, "the subscriber registers eagerly"

        frames = response.body_iterator
        first = await asyncio.wait_for(anext(frames), timeout=5)
        assert first.startswith("event: snapshot\ndata: ")
        assert json.loads(first.split("data: ", 1)[1])["payload"]["dashboard"]["slug"] == ("fleet")

        await streaming.notify_data_refresh(dashboard.id)
        second = await asyncio.wait_for(anext(frames), timeout=5)
        assert second.startswith("event: update\ndata: ")

        await frames.aclose()
        assert hub.count_for(dashboard.id) == 0, "closing the stream releases the subscriber"

    async def test_a_quiet_stream_still_emits_heartbeats(
        self, db_session: AsyncSession, resolver: WidgetResolver, publisher: RecordingPublisher
    ) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        hub = DashboardHub()
        streaming = StreamingService(
            hub,
            DashboardService(
                DashboardRepository(db_session),
                DashboardWidgetRepository(db_session),
                DashboardLayoutRepository(db_session),
                DashboardHistoryRepository(db_session),
                DashboardViewRepository(db_session),
                resolver,
                publish_event=publisher,
            ),
        )

        class _Settings:
            stream_heartbeat_seconds = 1

        class _State:
            service_settings = _Settings()

        class _App:
            state = _State()

        class _Request:
            app = _App()

        response = await stream_route(
            _Request(),  # type: ignore[arg-type]
            dashboard.id,
            streaming,
            None,
        )
        frames = response.body_iterator
        await asyncio.wait_for(anext(frames), timeout=5)  # the snapshot
        beat = await asyncio.wait_for(anext(frames), timeout=10)
        assert beat.startswith("event: heartbeat")
        await frames.aclose()

    def test_the_route_is_published_in_the_contract(self, sync_app: FastAPI) -> None:
        operation = sync_app.openapi()["paths"]["/dashboards/{dashboard_id}/stream"]["get"]
        assert operation["summary"] == "Live updates over Server-Sent Events"


class TestTopologyRoute:
    """The topology traversal endpoint against a stub driver."""

    def test_a_traversal_returns_a_graph(
        self, sync_app: FastAPI, jwt_keypair: tuple[str, str]
    ) -> None:
        access = token(uuid.uuid4(), jwt_keypair)
        with TestClient(sync_app) as client:
            sync_app.state.topology = TopologyReader(FakeDriver(topology_records(2)))
            response = client.post(
                "/dashboards/topology",
                params={"organization_id": str(ORG)},
                json={"root_id": "asset-1", "kind": "blast_radius", "depth": 3},
                headers={"Authorization": f"Bearer {access}"},
            )
        assert response.status_code == HTTP_OK
        data = response.json()["data"]
        assert data["node_count"] == 3
        assert data["truncated"] is False
        assert data["kind"] == "blast_radius"

    def test_a_truncated_graph_says_so(
        self, sync_app: FastAPI, jwt_keypair: tuple[str, str]
    ) -> None:
        # A viewer must know they are looking at a partial picture rather
        # than a complete one that happens to be small.
        access = token(uuid.uuid4(), jwt_keypair)
        with TestClient(sync_app) as client:
            sync_app.state.topology = TopologyReader(FakeDriver(topology_records(3)), max_nodes=3)
            response = client.post(
                "/dashboards/topology",
                params={"organization_id": str(ORG)},
                json={"root_id": "asset-1"},
                headers={"Authorization": f"Bearer {access}"},
            )
        body = response.json()
        assert body["data"]["truncated"] is True
        assert "truncated" in body["message"]

    def test_an_out_of_range_depth_is_refused_before_the_graph(
        self, sync_app: FastAPI, jwt_keypair: tuple[str, str]
    ) -> None:
        access = token(uuid.uuid4(), jwt_keypair)
        driver = FakeDriver()
        with TestClient(sync_app) as client:
            sync_app.state.topology = TopologyReader(driver, max_depth=2)
            response = client.post(
                "/dashboards/topology",
                params={"organization_id": str(ORG)},
                json={"root_id": "asset-1", "depth": 5},
                headers={"Authorization": f"Bearer {access}"},
            )
        assert response.status_code >= 400
        assert driver.queries == [], "an invalid depth must never reach Neo4j"

    def test_a_graph_failure_is_reported_as_a_dependency_error(
        self, sync_app: FastAPI, jwt_keypair: tuple[str, str]
    ) -> None:
        access = token(uuid.uuid4(), jwt_keypair)
        with TestClient(sync_app) as client:
            sync_app.state.topology = TopologyReader(
                FakeDriver(error=RuntimeError("neo4j is down"))
            )
            response = client.post(
                "/dashboards/topology",
                params={"organization_id": str(ORG)},
                json={"root_id": "asset-1"},
                headers={"Authorization": f"Bearer {access}"},
            )
        assert response.json()["error"]["code"] == "AIIOS-DEP-0001"


def test_the_app_starts_and_stops_with_every_subsystem(sync_app: FastAPI) -> None:
    """The real lifespan brings up and tears down cleanly.

    Covers the parts of the factory a request-scoped test never reaches:
    the hub, the broadcaster, the Neo4j driver, and both worker
    branches.
    """
    with TestClient(sync_app) as client:
        assert client.get("/health").status_code == HTTP_OK
        state: Any = sync_app.state
        assert state.hub is not None
        assert state.topology is not None
        assert state.jwt_public_key.startswith("-----BEGIN PUBLIC KEY-----")
        assert state.scheduler_manager is None, "disabled in tests to avoid a racing tick"
        assert state.refresh_worker is None, "exercised directly through its own tick()"
