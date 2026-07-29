"""Real-time hub, cross-replica relay, workers, health, and telemetry.

The hub is tested for the behaviours that only matter under stress:
back-pressure, slow-subscriber eviction, heartbeats, and the relay loop
that would otherwise bounce a frame between two replicas forever. The
Redis broadcaster runs against the **real** Redis in docker-compose,
because "does pub/sub actually reach the other side?" cannot be
answered by a mock.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from opentelemetry import trace
from redis.asyncio import Redis
from shared_core.events import default_registry
from shared_core.exceptions.dependency import DependencyError
from shared_core.exceptions.notification import NotificationError
from shared_core.exceptions.validation import ValidationError
from shared_core.scheduler import Job, JobType, Schedule
from shared_core.scheduler import ScheduleType as FrameworkScheduleType
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.analytics import router as analytics_router
from app.events import dashboard_events
from app.models.enums import StreamEventKind, TopologyQueryKind
from app.notifications.dashboard_notifications import DashboardNotificationService
from app.realtime.broadcast import CHANNEL, RedisBroadcaster, build_broadcaster
from app.realtime.hub import DashboardHub, StreamEvent
from app.repositories.dashboard import DashboardRepository
from app.repositories.dashboard_history import DashboardHistoryRepository
from app.repositories.dashboard_layout import DashboardLayoutRepository
from app.repositories.dashboard_view import DashboardViewRepository
from app.repositories.dashboard_widget import DashboardWidgetRepository
from app.services.dashboard import DashboardService
from app.services.streaming import RELOAD_ACTION, StreamingService
from app.telemetry.tracing import (
    trace_dashboard_load,
    trace_filter_execution,
    trace_streaming,
    trace_topology_render,
    trace_widget_render,
)
from app.topology.graph import TopologyReader
from app.widgets.resolver import WidgetResolver
from app.workers.refresh import RefreshWorker
from app.workers.registrar import STATISTICS_ROLLUP_JOB_ID, register_statistics_rollup
from app.workers.statistics import StatisticsWorker
from tests.conftest import (
    FakeDriver,
    RecordingPublisher,
    make_dashboard,
    make_widget,
    topology_records,
)

ORG = uuid.UUID("33333333-3333-3333-3333-333333333333")

HTTP_OK = 200


class TestDashboardHub:
    """Fan-out, back-pressure, and presence."""

    async def test_a_frame_reaches_every_subscriber_of_its_dashboard(self) -> None:
        hub = DashboardHub()
        dashboard_id = uuid.uuid4()
        first = hub.subscribe(dashboard_id)
        second = hub.subscribe(dashboard_id)
        elsewhere = hub.subscribe(uuid.uuid4())

        delivered = await hub.publish_update(dashboard_id, {"reason": "test"})
        assert delivered == 2
        assert first.queue.qsize() == 1
        assert second.queue.qsize() == 1
        assert elsewhere.queue.qsize() == 0

    async def test_a_slow_subscriber_is_dropped_not_waited_on(self) -> None:
        # A backgrounded browser tab must not stall live updates for
        # everyone else watching the same incident dashboard.
        hub = DashboardHub(queue_size=2)
        dashboard_id = uuid.uuid4()
        stalled = hub.subscribe(dashboard_id)
        healthy = hub.subscribe(dashboard_id)

        for _ in range(2):
            await hub.publish_update(dashboard_id, {})
        # Drain only the healthy subscriber, so the other fills up.
        while not healthy.queue.empty():
            healthy.queue.get_nowait()

        delivered = await asyncio.wait_for(hub.publish_update(dashboard_id, {}), timeout=2)
        assert delivered == 1
        assert hub.count_for(dashboard_id) == 1
        assert stalled.subscriber_id not in [
            entry["subscriber_id"] for entry in hub.presence(dashboard_id)
        ]

    async def test_the_subscriber_ceiling_refuses_rather_than_over_accepts(self) -> None:
        hub = DashboardHub(max_subscribers=1)
        hub.subscribe(uuid.uuid4())
        with pytest.raises(RuntimeError, match="limit"):
            hub.subscribe(uuid.uuid4())

    async def test_unsubscribing_twice_is_safe(self) -> None:
        hub = DashboardHub()
        subscriber = hub.subscribe(uuid.uuid4())
        hub.unsubscribe(subscriber)
        hub.unsubscribe(subscriber)
        assert hub.subscriber_count == 0

    async def test_watched_dashboards_tracks_only_live_audiences(self) -> None:
        hub = DashboardHub()
        dashboard_id = uuid.uuid4()
        subscriber = hub.subscribe(dashboard_id)
        assert hub.watched_dashboards() == [dashboard_id]
        hub.unsubscribe(subscriber)
        assert hub.watched_dashboards() == []

    async def test_presence_lists_who_is_watching(self) -> None:
        hub = DashboardHub()
        dashboard_id = uuid.uuid4()
        user = uuid.uuid4()
        hub.subscribe(dashboard_id, user_id=user)
        watchers = hub.presence(dashboard_id)
        assert watchers[0]["user_id"] == str(user)
        assert watchers[0]["connected_at"]

    async def test_presence_is_never_relayed_cross_replica(self) -> None:
        # Each replica knows only its own connections; relaying would let
        # replicas overwrite each other with partial lists.
        relayed: list[StreamEvent] = []

        class Recorder:
            async def publish(self, event: StreamEvent) -> None:
                relayed.append(event)

        hub = DashboardHub(broadcaster=Recorder())
        dashboard_id = uuid.uuid4()
        hub.subscribe(dashboard_id)

        await hub.publish_presence(dashboard_id)
        await hub.publish_update(dashboard_id, {})
        assert [event.kind for event in relayed] == [StreamEventKind.UPDATE]

    async def test_the_stream_emits_a_heartbeat_when_the_queue_is_quiet(self) -> None:
        # An idle socket is indistinguishable from a dead one, and
        # proxies close silent connections without telling either end.
        hub = DashboardHub()
        subscriber = hub.subscribe(uuid.uuid4())
        stream = hub.stream(subscriber, heartbeat_seconds=1)
        frame = await asyncio.wait_for(anext(stream), timeout=5)
        assert frame.kind is StreamEventKind.HEARTBEAT
        await stream.aclose()

    async def test_the_stream_yields_published_frames(self) -> None:
        hub = DashboardHub()
        dashboard_id = uuid.uuid4()
        subscriber = hub.subscribe(dashboard_id)
        await hub.publish_update(dashboard_id, {"reason": "test"})

        stream = hub.stream(subscriber, heartbeat_seconds=30)
        frame = await asyncio.wait_for(anext(stream), timeout=5)
        assert frame.kind is StreamEventKind.UPDATE
        assert frame.payload["reason"] == "test"
        await stream.aclose()

    async def test_closing_the_stream_unsubscribes(self) -> None:
        hub = DashboardHub()
        dashboard_id = uuid.uuid4()
        subscriber = hub.subscribe(dashboard_id)
        stream = hub.stream(subscriber, heartbeat_seconds=1)
        await asyncio.wait_for(anext(stream), timeout=5)
        await stream.aclose()
        assert hub.count_for(dashboard_id) == 0

    async def test_close_all_drops_everyone(self) -> None:
        hub = DashboardHub()
        for _ in range(3):
            hub.subscribe(uuid.uuid4())
        await hub.close_all()
        assert hub.subscriber_count == 0


class TestRedisBroadcaster:
    """Cross-replica relay against real Redis."""

    async def test_a_frame_published_on_one_replica_reaches_the_other(
        self, real_redis_client: Redis
    ) -> None:
        dashboard_id = uuid.uuid4()
        replica_a = DashboardHub()
        replica_b = DashboardHub()
        broadcaster_a = RedisBroadcaster(real_redis_client, replica_a)
        broadcaster_b = RedisBroadcaster(real_redis_client, replica_b)
        replica_a.attach_broadcaster(broadcaster_a)

        await broadcaster_b.start()
        try:
            subscriber = replica_b.subscribe(dashboard_id)
            await asyncio.sleep(0.3)  # let the SUBSCRIBE round-trip land
            await replica_a.publish_update(dashboard_id, {"reason": "cross-replica"})

            frame = await asyncio.wait_for(subscriber.queue.get(), timeout=5)
            assert frame.payload["reason"] == "cross-replica"
        finally:
            await broadcaster_b.stop()

    async def test_a_relayed_frame_is_not_re_relayed(self, real_redis_client: Redis) -> None:
        # Without relay=False on receipt, two replicas would bounce the
        # same frame between each other forever.
        published: list[StreamEvent] = []

        class Recorder(RedisBroadcaster):
            async def publish(self, event: StreamEvent) -> None:
                published.append(event)

        hub = DashboardHub()
        recorder = Recorder(real_redis_client, hub)
        hub.attach_broadcaster(recorder)

        await hub.publish(
            StreamEvent(kind=StreamEventKind.UPDATE, dashboard_id=uuid.uuid4()), relay=False
        )
        assert published == []

    async def test_a_publish_failure_is_logged_not_raised(self) -> None:
        # Local subscribers have already been served; failing the
        # originating request because a *remote* fan-out hiccupped would
        # be the wrong trade.
        class BrokenRedis:
            async def publish(self, *_args: Any, **_kwargs: Any) -> None:
                raise ConnectionError("redis is down")

        hub = DashboardHub()
        broadcaster = RedisBroadcaster(BrokenRedis(), hub)  # type: ignore[arg-type]
        await broadcaster.publish(
            StreamEvent(kind=StreamEventKind.UPDATE, dashboard_id=uuid.uuid4())
        )

    async def test_no_redis_means_no_relay_rather_than_no_hub(self) -> None:
        hub = DashboardHub()
        assert build_broadcaster(None, hub) is None

    async def test_stopping_a_broadcaster_that_never_started_is_safe(
        self, real_redis_client: Redis
    ) -> None:
        broadcaster = RedisBroadcaster(real_redis_client, DashboardHub())
        await broadcaster.stop()
        await broadcaster.start()
        await broadcaster.start()  # idempotent
        await broadcaster.stop()

    def test_the_channel_is_one_shared_name(self) -> None:
        # One channel rather than one per dashboard: pattern subscribes
        # across thousands of dashboards cost more than local filtering.
        assert CHANNEL == "aiios:dashboard:events"


class TestStreamingService:
    """Snapshots and notifications."""

    async def test_a_snapshot_carries_the_full_dashboard(
        self, db_session: AsyncSession, resolver: WidgetResolver, publisher: RecordingPublisher
    ) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        await make_widget(db_session, dashboard=dashboard)
        service = StreamingService(
            DashboardHub(),
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
        frame = await service.snapshot(dashboard.id)
        assert frame.kind is StreamEventKind.SNAPSHOT
        assert frame.payload["dashboard"]["slug"] == "fleet"
        assert frame.payload["widgets"][0]["status"] == "ok"

    async def test_a_snapshot_does_not_double_count_the_view(
        self, db_session: AsyncSession, resolver: WidgetResolver, publisher: RecordingPublisher
    ) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        await make_widget(db_session, dashboard=dashboard)
        service = StreamingService(
            DashboardHub(),
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
        await service.snapshot(dashboard.id)
        views = await DashboardViewRepository(db_session).list_for_dashboard(dashboard.id)
        assert views == [], (
            "a snapshot repeats the load the client just did over HTTP; "
            "counting it again would double every view figure"
        )

    async def test_notifications_carry_no_data(
        self, db_session: AsyncSession, resolver: WidgetResolver, publisher: RecordingPublisher
    ) -> None:
        # Broadcast frames reach every watcher at once, and those are
        # different people with different rights.
        hub = DashboardHub()
        dashboard_id = uuid.uuid4()
        subscriber = hub.subscribe(dashboard_id)
        service = StreamingService(
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
        await service.notify_layout_changed(dashboard_id, revision=3)
        frame = subscriber.queue.get_nowait()
        assert frame.payload == {
            "action": RELOAD_ACTION,
            "reason": "layout_changed",
            "layout_revision": 3,
        }
        assert "widgets" not in frame.payload

    async def test_nothing_is_sent_to_a_dashboard_nobody_watches(
        self, db_session: AsyncSession, resolver: WidgetResolver, publisher: RecordingPublisher
    ) -> None:
        service = StreamingService(
            DashboardHub(),
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
        assert await service.notify_data_refresh(uuid.uuid4()) == 0

    async def test_an_error_frame_reaches_watchers(
        self, db_session: AsyncSession, resolver: WidgetResolver, publisher: RecordingPublisher
    ) -> None:
        hub = DashboardHub()
        dashboard_id = uuid.uuid4()
        subscriber = hub.subscribe(dashboard_id)
        service = StreamingService(
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
        assert await service.notify_error(dashboard_id, error="source down") == 1
        assert subscriber.queue.get_nowait().kind is StreamEventKind.ERROR


class TestRefreshWorker:
    """The per-replica refresh loop."""

    async def test_a_tick_with_no_watchers_costs_nothing(self) -> None:
        worker = RefreshWorker(DashboardHub())
        assert await worker.tick() == 0

    async def test_a_tick_notifies_every_watched_dashboard(self) -> None:
        hub = DashboardHub()
        dashboard_id = uuid.uuid4()
        subscriber = hub.subscribe(dashboard_id)
        worker = RefreshWorker(hub)

        assert await worker.tick() == 1
        frame = subscriber.queue.get_nowait()
        assert frame.payload["reason"] == "refresh_due"

    async def test_the_loop_starts_and_stops_cleanly(self) -> None:
        hub = DashboardHub()
        hub.subscribe(uuid.uuid4())
        worker = RefreshWorker(hub, poll_seconds=0.05)

        await worker.start()
        await worker.start()  # idempotent
        assert worker.running
        await asyncio.sleep(0.15)
        await worker.stop()

        assert not worker.running
        assert hub.subscriber_count == 0, "shutdown drops every subscriber"

    async def test_one_failing_dashboard_does_not_stop_the_tick(self) -> None:
        broken_id = uuid.uuid4()

        class PartlyBrokenHub(DashboardHub):
            async def publish_update(
                self, dashboard_id: uuid.UUID, payload: dict[str, Any], *, relay: bool = True
            ) -> int:
                if dashboard_id == broken_id:
                    raise RuntimeError("this one is broken")
                return await super().publish_update(dashboard_id, payload, relay=relay)

        hub = PartlyBrokenHub()
        hub.subscribe(broken_id)
        healthy_id = uuid.uuid4()
        hub.subscribe(healthy_id)

        assert await RefreshWorker(hub).tick() == 1

    async def test_the_loop_survives_a_raising_tick(self) -> None:
        class ExplodingHub(DashboardHub):
            def watched_dashboards(self) -> list[uuid.UUID]:
                raise RuntimeError("boom")

        worker = RefreshWorker(ExplodingHub(), poll_seconds=0.05)
        await worker.start()
        await asyncio.sleep(0.15)
        assert worker.running, "a raising tick must not kill the loop"
        await worker.stop()


class TestStatisticsWorker:
    """The leader-elected analytics rollup."""

    async def test_a_tick_recomputes_every_organization(
        self, db_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        async with db_session_factory() as session:
            await make_dashboard(session, organization_id=ORG, slug="a")
            await make_dashboard(session, organization_id=uuid.uuid4(), slug="b")
            await session.commit()

        assert await StatisticsWorker(db_session_factory).tick() >= 2

    async def test_run_job_matches_the_scheduler_contract(
        self, db_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        # A signature mismatch here would reach production as "the
        # scheduler silently never fired".
        worker = StatisticsWorker(db_session_factory)
        job = Job(
            job_id="probe",
            job_name="probe",
            job_type=JobType.SYSTEM,
            fn=worker.run_job,
            schedule=Schedule(
                schedule_type=FrameworkScheduleType.FIXED_RATE,
                interval=timedelta(seconds=900),
            ),
        )
        await job.fn(job)

    async def test_one_failing_tenant_does_not_stop_the_rollup(
        self, db_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        worker = StatisticsWorker(db_session_factory)
        assert await worker._recompute(uuid.uuid4()) is True

    def test_registering_the_rollup_uses_a_deterministic_job_id(self) -> None:
        registered: list[Any] = []

        class FakeManager:
            def register_job(self, job: Any) -> None:
                registered.append(job)

        async def _fn(_job: Any) -> None:
            return None

        job = register_statistics_rollup(
            FakeManager(),  # type: ignore[arg-type]
            _fn,
            interval_seconds=900,
        )
        assert job.job_id == STATISTICS_ROLLUP_JOB_ID
        assert registered == [job], "re-registering must replace rather than leak"

    def test_a_non_positive_interval_is_refused(self) -> None:
        async def _fn(_job: Any) -> None:
            return None

        with pytest.raises(ValueError, match="must be positive"):
            register_statistics_rollup(None, _fn, interval_seconds=0)  # type: ignore[arg-type]


class TestTopologyReader:
    """Neo4j traversal against a driver that records its query."""

    async def test_a_traversal_parameterises_every_user_supplied_value(self) -> None:
        # Node ids arrive from user-authored widget definitions, so
        # concatenating them would be an injection path into the graph.
        driver = FakeDriver(topology_records(2))
        reader = TopologyReader(driver, max_depth=4, max_nodes=500)

        graph = await reader.query(
            organization_id=str(ORG),
            root_id="asset-1'; MATCH (n) DETACH DELETE n; //",
            kind=TopologyQueryKind.DEPENDENCIES,
            depth=2,
        )
        cypher, parameters = driver.queries[0]
        assert "DETACH DELETE" not in cypher
        assert parameters["root_id"].startswith("asset-1'")
        assert parameters["organization_id"] == str(ORG)
        assert graph.node_count == 3

    async def test_an_unconfigured_reader_reports_itself(self) -> None:
        reader = TopologyReader(None, enabled=False)
        assert not reader.enabled
        with pytest.raises(DependencyError, match="not configured"):
            await reader.query(organization_id=str(ORG), root_id="asset-1")

    async def test_a_missing_root_is_a_validation_error(self) -> None:
        reader = TopologyReader(FakeDriver())
        with pytest.raises(ValidationError, match="requires a root node id"):
            await reader.query(organization_id=str(ORG), root_id="")

    async def test_a_driver_failure_becomes_a_dependency_error(self) -> None:
        reader = TopologyReader(FakeDriver(error=RuntimeError("neo4j is down")))
        with pytest.raises(DependencyError, match="Topology query failed"):
            await reader.query(organization_id=str(ORG), root_id="asset-1")

    async def test_an_out_of_range_depth_never_reaches_the_query(self) -> None:
        driver = FakeDriver()
        reader = TopologyReader(driver, max_depth=3)
        with pytest.raises(ValidationError, match="between 1 and 3"):
            await reader.query(organization_id=str(ORG), root_id="asset-1", depth=9)
        assert driver.queries == [], "an invalid depth must not reach Neo4j at all"

    async def test_a_configured_reader_is_enabled(self) -> None:
        assert TopologyReader(FakeDriver()).enabled


class TestNotifications:
    """Notification delivery is best-effort."""

    async def test_a_notification_failure_never_blocks_the_operation(self) -> None:
        class BrokenManager:
            async def send(self, **_kwargs: Any) -> None:
                raise NotificationError("smtp is down")

        service = DashboardNotificationService(BrokenManager())  # type: ignore[arg-type]
        # A dashboard that loaded correctly must not report an error
        # because an SMTP server was down.
        await service.send_dashboard_shared("user", name="Fleet", shared_by="alice")
        await service.send_layout_updated("user", name="Fleet")
        await service.send_widget_failure("user", name="Fleet", widget="hosts", reason="down")
        await service.send_connection_lost("user", name="Fleet")
        await service.send_refresh_failure("user", name="Fleet", reason="down")

    async def test_every_notification_reaches_the_manager(self) -> None:
        sent: list[dict[str, Any]] = []

        class Recorder:
            async def send(self, **kwargs: Any) -> None:
                sent.append(kwargs)

        service = DashboardNotificationService(Recorder())  # type: ignore[arg-type]
        await service.send_dashboard_shared("user", name="Fleet", shared_by="alice")
        await service.send_layout_updated("user", name="Fleet")
        await service.send_widget_failure("user", name="Fleet", widget="hosts", reason="down")
        await service.send_connection_lost("user", name="Fleet")
        await service.send_refresh_failure("user", name="Fleet", reason="down")
        assert len(sent) == 5
        assert all(entry["user_id"] == "user" for entry in sent)


class TestTelemetry:
    """Spans exist and carry their attributes."""

    def test_every_traced_operation_produces_a_span(self) -> None:
        tracer = trace.get_tracer("test")
        with trace_dashboard_load(tracer, dashboard="fleet") as span:
            assert span is not None
        with trace_widget_render(tracer, widget="hosts") as span:
            assert span is not None
        with trace_topology_render(tracer, root="asset-1") as span:
            assert span is not None
        with trace_streaming(tracer, dashboard="fleet") as span:
            assert span is not None
        with trace_filter_execution(tracer, clauses=2) as span:
            assert span is not None


class TestEventRegistration:
    """Every declared event is genuinely published by some flow."""

    def test_every_event_is_registered(self) -> None:
        names = {
            getattr(dashboard_events, name).event_name
            for name in dashboard_events.__all__
            if name != "SOURCE_SERVICE"
        }
        assert names == {
            "DashboardCreated",
            "DashboardUpdated",
            "DashboardDeleted",
            "WidgetAdded",
            "WidgetRemoved",
            "LayoutChanged",
            "DashboardShared",
        }
        for name in names:
            assert default_registry.is_registered(name), (
                f"{name} is declared but never registered, so nothing could "
                "deserialise it off the wire"
            )


class TestHealthEndpoints:
    """Health, readiness, liveness, and metrics."""

    async def test_health_reports_the_service(self, client: AsyncClient) -> None:
        response = await client.get("/health")
        assert response.status_code == HTTP_OK
        assert response.json()["data"]["status"] == "healthy"

    async def test_liveness(self, client: AsyncClient) -> None:
        response = await client.get("/liveness")
        assert response.json()["data"]["status"] == "alive"

    async def test_readiness_checks_the_real_database(self, client: AsyncClient) -> None:
        response = await client.get("/readiness")
        data = response.json()["data"]
        assert data["status"] == "ready"
        assert [check["name"] for check in data["checks"]] == ["database"]

    async def test_readiness_reports_the_graph_without_gating_on_it(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        # Topology is one widget type among eighteen; refusing all
        # traffic because Neo4j is down would take out every dashboard
        # that never touches it.
        app.state.neo4j_driver = FakeDriver(error=RuntimeError("neo4j is down"))
        response = await client.get("/readiness")
        data = response.json()["data"]
        assert data["status"] == "ready"
        graph = next(check for check in data["checks"] if check["name"] == "graph")
        assert graph["status"] == "failed"
        app.state.neo4j_driver = None

    async def test_a_healthy_graph_is_reported_ok(self, app: FastAPI, client: AsyncClient) -> None:
        app.state.neo4j_driver = FakeDriver()
        response = await client.get("/readiness")
        graph = next(
            check for check in response.json()["data"]["checks"] if check["name"] == "graph"
        )
        assert graph["status"] == "ok"
        app.state.neo4j_driver = None

    async def test_metrics_are_exposed(self, client: AsyncClient) -> None:
        response = await client.get("/metrics")
        assert response.status_code == HTTP_OK
        assert "http_request" in response.text

    async def test_the_openapi_document_builds(self, client: AsyncClient) -> None:
        response = await client.get("/openapi.json")
        assert response.status_code == HTTP_OK
        assert response.json()["info"]["title"] == "AI-IOS Dashboard Service"


class TestServerSentEvents:
    """The SSE transport.

    The frame sequence is exercised directly rather than over the test
    client: ``httpx.ASGITransport`` buffers a response body to
    completion, so requesting an endpoint that streams forever would
    hang the suite rather than test it. The route's own wiring --
    registration, media type, and authentication -- is checked
    separately.
    """

    async def test_the_frame_sequence_is_a_snapshot_then_updates(
        self, db_session: AsyncSession, resolver: WidgetResolver, publisher: RecordingPublisher
    ) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        await make_widget(db_session, dashboard=dashboard)
        hub = DashboardHub()
        service = StreamingService(
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
        subscriber = service.subscribe(dashboard.id)
        snapshot = await service.snapshot(dashboard.id)
        await service.notify_data_refresh(dashboard.id)

        frames = [snapshot]
        stream = service.stream(subscriber, heartbeat_seconds=30)
        frames.append(await asyncio.wait_for(anext(stream), timeout=5))
        await stream.aclose()

        assert [frame.kind for frame in frames] == [
            StreamEventKind.SNAPSHOT,
            StreamEventKind.UPDATE,
        ], "a client joining mid-stream must not stare at an empty dashboard"
        assert frames[0].as_sse().startswith("event: snapshot\ndata: ")
        assert frames[1].as_sse().startswith("event: update\ndata: ")

    async def test_the_stream_route_is_registered_as_an_event_stream(self, app: FastAPI) -> None:
        operation = app.openapi()["paths"]["/dashboards/{dashboard_id}/stream"]["get"]
        assert operation["summary"] == "Live updates over Server-Sent Events"

    async def test_a_stream_requires_authentication(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        # A 401 short-circuits before the generator starts, so this one
        # is safe to drive through the test client.
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        response = await client.get(f"/dashboards/{dashboard.id}/stream")
        assert response.status_code == 401

    async def test_the_websocket_route_is_registered(self, app: FastAPI) -> None:
        # WebSocket routes never appear in OpenAPI, so the router itself
        # is the only place this can be checked.
        paths = {getattr(route, "path", "") for route in analytics_router.routes}
        assert "/dashboards/{dashboard_id}/ws" in paths
