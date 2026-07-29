"""Application factory.

Assembles the FastAPI application: configuration, logging, PostgreSQL,
Redis, events, notifications, the Neo4j driver and graph client, the
graph schema, the JWT verification key, middleware, exception handlers,
routers, the synchronization worker, and Prometheus instrumentation.

**The graph schema is applied at startup, and never fatally.** A
deployment where Neo4j is briefly unavailable should come up and report
itself not-ready rather than crash-loop, so a schema failure is logged
and the service continues. Everything is re-applied on the next start,
and every statement is ``IF NOT EXISTS``.

**Router order is load-bearing.** docs/049 specifies both
``/graph/nodes/{id}`` and literal collections like
``/graph/topology``; FastAPI matches in registration order, so the
literal-segment routers are included first. See :mod:`app.api.__init__`.
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

from app.api import admin_router, graph_router, health_router, query_router
from app.config.keys import load_public_key
from app.config.settings import Settings, get_settings
from app.graph.client import GraphClient, create_neo4j_driver
from app.graph.schema import apply_schema
from app.middleware.timing import TimingMiddleware
from app.workers.registrar import register_statistics_rollup
from app.workers.statistics import StatisticsWorker

logger = get_logger("app.startup")


def build_graph_client(driver: object | None, settings: Settings) -> GraphClient:
    """Build the process-wide Neo4j client."""
    return GraphClient(
        driver,  # type: ignore[arg-type]
        database=settings.service.neo4j_database,
        max_records=settings.service.max_result_nodes,
        timeout_seconds=settings.service.query_timeout_seconds,
        enabled=settings.service.neo4j_enabled,
    )


async def _build_scheduler(
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: Redis,
    settings: Settings,
) -> SchedulerManager | None:
    """Register and start the leader-elected statistics rollup.

    Leader-elected because the rollup is a pure database write with no
    per-replica state: N replicas computing it would be N times the load
    for an identical result, and two concurrent recomputes of one
    organization would race on the same row.
    """
    if not settings.service.scheduler_enabled:
        return None
    queue = await create_queue_framework(settings.rabbitmq)
    manager = create_scheduler_framework(
        queue.manager, redis_client, queue_name="knowledge_graph_scheduler_queue"
    )
    register_statistics_rollup(
        manager,
        StatisticsWorker(session_factory, graph_settings=settings.service).run_job,
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

    # Synchronization runs unattended, so it carries a service token
    # rather than a caller's. See app/clients/platform.py for what that
    # means for what the mappers are allowed to project into the graph.
    app.state.service_token = settings.service.sync_service_token
    if settings.service.sync_enabled and not app.state.service_token:
        logger.warning(
            "Synchronization is enabled but no service token is configured; "
            "every source will refuse the read. Set "
            "AIIOS_KNOWLEDGE_GRAPH_SERVICE_SYNC_SERVICE_TOKEN.",
        )

    driver = create_neo4j_driver(
        settings.neo4j,
        enabled=settings.service.neo4j_enabled,
        max_pool_size=settings.service.neo4j_max_connection_pool_size,
        connection_timeout=settings.service.neo4j_connection_timeout_seconds,
    )
    app.state.neo4j_driver = driver
    app.state.graph_client = build_graph_client(driver, settings)
    await apply_schema(app.state.graph_client)

    scheduler_manager = await _build_scheduler(database.session_factory, cache.client, settings)
    app.state.scheduler_manager = scheduler_manager

    logger.info(
        "knowledge-graph-service starting up",
        extra={
            "extra_fields": {
                "graph": app.state.graph_client.enabled,
                "neo4j_database": settings.service.neo4j_database,
                "custom_cypher": settings.service.allow_custom_cypher,
                "scheduler_enabled": settings.service.scheduler_enabled,
            }
        },
    )
    try:
        yield
    finally:
        if scheduler_manager is not None:
            await scheduler_manager.stop()
        if driver is not None:
            await driver.close()
        await database.shutdown()
        await cache.shutdown()
        await events.shutdown()
        await app.state.http_client.aclose()
        logger.info("knowledge-graph-service shutting down")


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    settings = get_settings()
    configure_logging(
        service=settings.application.app_name,
        environment=settings.application.environment,
        level=settings.application.log_level,
    )

    app = FastAPI(
        title="AI-IOS Knowledge Graph Service",
        description=(
            "Enterprise knowledge graph -- Neo4j graph model over forty node "
            "types and twenty relationship types, digital twins, dependency, "
            "impact and blast-radius analysis, graph analytics, synchronization "
            "from ten platform services, snapshots and versioning, import/export "
            "in four formats, and read-only Cypher."
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
    app.include_router(query_router)
    app.include_router(admin_router)
    app.include_router(graph_router)

    Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=True)

    return app


def _build_cors_config(settings: Settings) -> CorsConfig:
    """Build the CORS policy for the current environment."""
    if settings.application.environment.value == "production":
        return production_cors_config(settings.service.cors_allowed_origins)
    return development_cors_config()


__all__ = ["build_graph_client", "create_app"]
