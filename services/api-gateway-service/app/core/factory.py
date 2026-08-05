"""Application factory.

Assembles the FastAPI application: configuration, logging, PostgreSQL,
Redis, events, the outbound HTTP client the proxy forwards through, the
JWT verification key, process-wide circuit breakers and load-balancing
state, the WebSocket hub, middleware, exception handlers, routers, the
background workers, and Prometheus instrumentation.

**The reverse-proxy catch-all is mounted dead last**, after every
management router (including GraphQL and the WebSocket route) -- it
matches every path and method, mirroring notification-center-service's
own hard-learned router-ordering lesson: a route matching everything
would otherwise swallow this service's own management endpoints if
registered before them.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator
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
from shared_core.queue.factory import create_queue_framework
from shared_core.scheduler import SchedulerManager
from shared_core.scheduler.factory import create_scheduler_framework
from shared_core.security.cors import CorsConfig, development_cors_config, production_cors_config
from shared_core.validation.middleware import RequestValidationMiddleware
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.middleware.cors import CORSMiddleware

from app.api import MANAGEMENT_ROUTERS, proxy_router
from app.config.keys import load_public_key
from app.config.settings import Settings, get_settings
from app.websocket.hub import GatewayHub
from app.workers.health_probe_sweep import HealthProbeSweepWorker
from app.workers.quota_reset_sweep import QuotaResetSweepWorker
from app.workers.registrar import (
    register_health_probe_sweep,
    register_quota_reset_sweep,
    register_statistics_rollup,
)
from app.workers.statistics_rollup import StatisticsRollupWorker

logger = get_logger("app.startup")


async def _build_workers(
    session_factory: async_sessionmaker[AsyncSession],
    breakers: dict[str, object],
    redis_client: object,
    settings: Settings,
    publish_event: object,
) -> SchedulerManager | None:
    """Register and start the leader-elected background jobs.

    All three are leader-elected: each is pure database (plus, for the
    health sweep, outbound HTTP) work with no per-replica state, so N
    replicas would be N times the load for an identical result.
    """
    if not settings.service.workers_enabled:
        return None

    queue = await create_queue_framework(settings.rabbitmq)
    manager = create_scheduler_framework(
        queue.manager, redis_client, queue_name="api_gateway_service_scheduler_queue"
    )
    register_health_probe_sweep(
        manager,
        HealthProbeSweepWorker(
            session_factory,
            breakers,  # type: ignore[arg-type]
            settings.service,
            publish_event=publish_event,  # type: ignore[arg-type]
        ).run_job,
        interval_seconds=settings.service.health_probe_sweep_seconds,
    )
    register_statistics_rollup(
        manager,
        StatisticsRollupWorker(
            session_factory, window_seconds=settings.service.statistics_rollup_seconds
        ).run_job,
        interval_seconds=settings.service.statistics_rollup_seconds,
    )
    register_quota_reset_sweep(
        manager,
        QuotaResetSweepWorker(session_factory).run_job,
        interval_seconds=settings.service.quota_reset_sweep_seconds,
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

    app.state.http_client = httpx.AsyncClient(
        limits=httpx.Limits(
            max_connections=settings.service.upstream_max_connections,
            max_keepalive_connections=settings.service.upstream_max_keepalive_connections,
        ),
        timeout=httpx.Timeout(
            connect=settings.service.upstream_connect_timeout_seconds,
            read=settings.service.upstream_read_timeout_seconds,
            write=settings.service.upstream_read_timeout_seconds,
            pool=settings.service.upstream_connect_timeout_seconds,
        ),
    )

    app.state.jwt_public_key = load_public_key(settings.service.jwt_public_key_path)
    app.state.service_settings = settings.service

    # Process-wide, request/worker-shared state -- see
    # `app/services/health.py` and `app/api/deps.py` for why circuit
    # breakers cannot themselves be request-scoped, and
    # `app/services/proxy.py` for the load-balancing counters/sticky maps.
    app.state.circuit_breakers = {}
    app.state.round_robin_counters = {}
    app.state.sticky_maps = {}
    app.state.websocket_hub = GatewayHub()

    scheduler_manager = await _build_workers(
        database.session_factory,
        app.state.circuit_breakers,
        cache.client,
        settings,
        events.manager.publish,
    )
    app.state.scheduler_manager = scheduler_manager

    logger.info(
        "api-gateway-service starting up",
        extra={
            "extra_fields": {
                "workers_enabled": settings.service.workers_enabled,
                "health_probe_sweep_seconds": settings.service.health_probe_sweep_seconds,
                "statistics_rollup_seconds": settings.service.statistics_rollup_seconds,
                "quota_reset_sweep_seconds": settings.service.quota_reset_sweep_seconds,
            }
        },
    )
    try:
        yield
    finally:
        if scheduler_manager is not None:
            await scheduler_manager.stop()
        await app.state.websocket_hub.close_all()
        await app.state.http_client.aclose()
        await database.shutdown()
        await cache.shutdown()
        await events.shutdown()
        logger.info("api-gateway-service shutting down")


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    settings = get_settings()
    configure_logging(
        service=settings.application.app_name,
        environment=settings.application.environment,
        level=settings.application.log_level,
    )

    app = FastAPI(
        title="AI-IOS Enterprise API Gateway Service",
        description=(
            "Single entry point for every backend service: routing, load "
            "balancing, authentication/authorization, rate limiting, "
            "quotas, circuit breaking, request/response transformation, "
            "a REST management API, a GraphQL query surface, and a "
            "WebSocket live event stream. See this package's own README."
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
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(LocalizationMiddleware)
    app.add_middleware(RequestValidationMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)

    register_exception_handlers(app)

    for router in MANAGEMENT_ROUTERS:
        app.include_router(router)

    # See this module's own docstring: `proxy_router` matches every path
    # and method, so it must be registered strictly last.
    app.include_router(proxy_router)

    Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=True)

    return app


def _build_cors_config(settings: Settings) -> CorsConfig:
    """Build the CORS policy for the current environment."""
    if settings.application.environment.value == "production":
        return production_cors_config(settings.service.cors_allowed_origins)
    return development_cors_config()


__all__ = ["create_app"]
