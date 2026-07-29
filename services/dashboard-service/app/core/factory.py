"""Application factory.

Assembles the FastAPI application: configuration, logging, database,
cache, events, notifications, the Neo4j driver behind topology widgets,
the JWT verification key, the process-wide real-time hub and its
cross-replica broadcaster, middleware, exception handlers, routers,
both workers, and Prometheus instrumentation.

**Two workers with deliberately opposite scaling behaviour.**
:class:`~app.workers.statistics.StatisticsWorker` runs through
``shared_core.scheduler`` and is leader-elected, because N replicas
computing the same rollup would be N times the load for an identical
result. :class:`~app.workers.refresh.RefreshWorker` runs its own loop
on *every* replica, because subscribers live in the process that
accepted their connection and an elected replica would refresh only its
own watchers.

**Router order is load-bearing.** docs/048 specifies both
``/dashboards/{id}`` and literal collections like
``/dashboards/statistics``; FastAPI matches in registration order, so
the literal-segment routers are included first. See
:mod:`app.api.__init__`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator
from redis.asyncio import Redis
from shared_core.cache.factory import create_cache_framework
from shared_core.cache.settings import CacheSettings
from shared_core.database.factory import create_database_framework
from shared_core.events.factory import create_event_framework
from shared_core.exceptions import register_exception_handlers
from shared_core.logging import configure_logging, get_logger
from shared_core.middleware import (
    LocalizationMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)
from shared_core.notifications.factory import create_notification_framework
from shared_core.queue.factory import create_queue_framework
from shared_core.scheduler import SchedulerManager
from shared_core.scheduler.factory import create_scheduler_framework
from shared_core.security.cors import CorsConfig, development_cors_config, production_cors_config
from shared_core.validation.middleware import RequestValidationMiddleware
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.middleware.cors import CORSMiddleware

from app.api import (
    analytics_router,
    catalog_router,
    dashboards_router,
    health_router,
    sharing_router,
)
from app.config.keys import load_public_key
from app.config.settings import Settings, get_settings
from app.middleware.timing import TimingMiddleware
from app.realtime.broadcast import RedisBroadcaster, build_broadcaster
from app.realtime.hub import DashboardHub
from app.topology.client import create_neo4j_driver
from app.topology.graph import TopologyReader
from app.workers.refresh import RefreshWorker
from app.workers.registrar import register_statistics_rollup
from app.workers.statistics import StatisticsWorker

logger = get_logger("app.startup")


def _build_topology_reader(driver: object | None, settings: Settings) -> TopologyReader:
    """Build the topology reader behind topology widgets."""
    return TopologyReader(
        driver,
        max_depth=settings.service.topology_max_depth,
        max_nodes=settings.service.topology_max_nodes,
        enabled=settings.service.topology_enabled,
    )


async def _build_realtime(
    redis_client: object | None, settings: Settings
) -> tuple[DashboardHub, RedisBroadcaster | None]:
    """Build the real-time hub and start cross-replica relay.

    The broadcaster is attached after construction rather than passed
    in, because it has to be told which hub to deliver into -- one of
    the two must exist first, and building the hub twice would leave the
    first holding subscribers nothing ever reaches.
    """
    hub = DashboardHub(max_subscribers=settings.service.stream_max_subscribers)
    broadcaster = build_broadcaster(
        redis_client if settings.service.realtime_enabled else None, hub
    )
    hub.attach_broadcaster(broadcaster)
    if broadcaster is not None:
        await broadcaster.start()
    return hub, broadcaster


async def _build_scheduler(
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: Redis,
    settings: Settings,
) -> SchedulerManager | None:
    """Register and start the leader-elected analytics rollup."""
    if not settings.service.scheduler_enabled:
        return None
    queue = await create_queue_framework(settings.rabbitmq)
    manager = create_scheduler_framework(
        queue.manager, redis_client, queue_name="dashboard_scheduler_queue"
    )
    register_statistics_rollup(
        manager,
        StatisticsWorker(
            session_factory, window_days=settings.service.analytics_window_days
        ).run_job,
        interval_seconds=settings.service.statistics_rollup_seconds,
    )
    await manager.start()
    return manager


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()

    database = await create_database_framework(settings.database)
    app.state.db_engine = database.engine
    app.state.db_session_factory = database.session_factory

    cache = await create_cache_framework(CacheSettings(redis=settings.redis))
    app.state.cache_manager = cache.manager
    app.state.redis_client = cache.client

    events = await create_event_framework(settings.rabbitmq)
    app.state.publish_event = events.manager.publish

    app.state.notification_manager = create_notification_framework(email_settings=settings.email)
    app.state.jwt_public_key = load_public_key(settings.service.jwt_public_key_path)
    app.state.service_settings = settings.service
    app.state.http_client = httpx.AsyncClient(timeout=settings.service.http_client_timeout_seconds)

    driver = create_neo4j_driver(settings.neo4j, enabled=settings.service.topology_enabled)
    app.state.neo4j_driver = driver
    app.state.topology = _build_topology_reader(driver, settings)

    hub, broadcaster = await _build_realtime(cache.client, settings)
    app.state.hub = hub
    app.state.broadcaster = broadcaster

    refresh_worker: RefreshWorker | None = None
    if settings.service.realtime_enabled and settings.service.refresh_worker_enabled:
        refresh_worker = RefreshWorker(hub, poll_seconds=settings.service.refresh_poll_seconds)
        await refresh_worker.start()
    app.state.refresh_worker = refresh_worker

    scheduler_manager = await _build_scheduler(database.session_factory, cache.client, settings)
    app.state.scheduler_manager = scheduler_manager

    logger.info(
        "dashboard-service starting up",
        extra={
            "extra_fields": {
                "topology": app.state.topology.enabled,
                "realtime": settings.service.realtime_enabled,
                "cross_replica_relay": broadcaster is not None,
                "refresh_worker": refresh_worker is not None,
                "scheduler_enabled": settings.service.scheduler_enabled,
            }
        },
    )
    try:
        yield
    finally:
        if scheduler_manager is not None:
            await scheduler_manager.stop()
        if refresh_worker is not None:
            await refresh_worker.stop()
        if broadcaster is not None:
            await broadcaster.stop()
        if driver is not None:
            await driver.close()
        await database.shutdown()
        await cache.shutdown()
        await events.shutdown()
        await app.state.http_client.aclose()
        logger.info("dashboard-service shutting down")


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    settings = get_settings()
    configure_logging(
        service=settings.application.app_name,
        environment=settings.application.environment,
        level=settings.application.log_level,
    )

    app = FastAPI(
        title="AI-IOS Dashboard Service",
        description=(
            "Enterprise dashboard platform -- drag-and-drop builder, eighteen widget "
            "types over thirteen data sources, responsive per-breakpoint layouts with "
            "undo/redo, topology visualisation, real-time updates over SSE and "
            "WebSocket, themes with WCAG contrast auditing, templates, sharing, and "
            "usage analytics."
        ),
        version=settings.application.app_version,
        docs_url="/docs",
        openapi_url="/openapi.json",
        lifespan=_lifespan,
    )

    cors_config = _build_cors_config(settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(cors_config.allow_origins),
        allow_methods=list(cors_config.allow_methods),
        allow_headers=list(cors_config.allow_headers),
        allow_credentials=cors_config.allow_credentials,
        max_age=cors_config.max_age_seconds,
    )
    app.add_middleware(TimingMiddleware)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(LocalizationMiddleware)
    app.add_middleware(RequestValidationMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)

    register_exception_handlers(app)

    # Literal-segment routers first; see this module's docstring.
    app.include_router(health_router)
    app.include_router(catalog_router)
    app.include_router(sharing_router)
    app.include_router(analytics_router)
    app.include_router(dashboards_router)

    Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=True)

    return app


def _build_cors_config(settings: Settings) -> CorsConfig:
    """Build the CORS policy for the current environment."""
    if settings.application.environment.value == "production":
        return production_cors_config(settings.service.cors_allowed_origins)
    return development_cors_config()


__all__ = ["create_app"]
