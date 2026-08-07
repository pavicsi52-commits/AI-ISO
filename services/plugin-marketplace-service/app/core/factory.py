"""Application factory.

Assembles the FastAPI application: configuration, logging, PostgreSQL,
Redis, events, MinIO (plugin package storage), the JWT verification key,
middleware, exception handlers, routers, the background workers, and
Prometheus instrumentation.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

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
from shared_core.queue.factory import create_queue_framework
from shared_core.scheduler import SchedulerManager
from shared_core.scheduler.factory import create_scheduler_framework
from shared_core.security.cors import CorsConfig, development_cors_config, production_cors_config
from shared_core.storage import create_minio_client
from shared_core.validation.middleware import RequestValidationMiddleware
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.middleware.cors import CORSMiddleware

from app.api import ALL_ROUTERS
from app.config.keys import load_public_key
from app.config.settings import Settings, get_settings
from app.types import EventPublisher
from app.workers.health_probe_sweep import HealthProbeSweepWorker
from app.workers.marketplace_approval_sweep import MarketplaceApprovalSweepWorker
from app.workers.registrar import (
    register_health_probe_sweep,
    register_marketplace_approval_sweep,
    register_review_moderation_sweep,
    register_statistics_rollup,
)
from app.workers.review_moderation_sweep import ReviewModerationSweepWorker
from app.workers.statistics_rollup import StatisticsRollupWorker

logger = get_logger("app.startup")


async def _build_workers(
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: Redis,
    settings: Settings,
    publish_event: EventPublisher,
) -> SchedulerManager | None:
    """Register and start the leader-elected background jobs.

    All four are leader-elected: each is pure database (plus, for the
    health probe, outbound HTTP) work with no per-replica state, so N
    replicas would be N times the load for an identical result.
    """
    if not settings.service.workers_enabled:
        return None

    queue = await create_queue_framework(settings.rabbitmq)
    manager = create_scheduler_framework(
        queue.manager, redis_client, queue_name="plugin_marketplace_service_scheduler_queue"
    )
    register_health_probe_sweep(
        manager,
        HealthProbeSweepWorker(
            session_factory,
            timeout_seconds=settings.service.health_check_timeout_seconds,
            failure_threshold=settings.service.health_failure_threshold,
            publish_event=publish_event,
        ).run_job,
        interval_seconds=settings.service.health_probe_sweep_seconds,
    )
    register_marketplace_approval_sweep(
        manager,
        MarketplaceApprovalSweepWorker(session_factory, publish_event=publish_event).run_job,
        interval_seconds=settings.service.marketplace_approval_sweep_seconds,
    )
    register_statistics_rollup(
        manager,
        StatisticsRollupWorker(
            session_factory, window_seconds=settings.service.statistics_rollup_seconds
        ).run_job,
        interval_seconds=settings.service.statistics_rollup_seconds,
    )
    register_review_moderation_sweep(
        manager,
        ReviewModerationSweepWorker(session_factory).run_job,
        interval_seconds=settings.service.review_moderation_sweep_seconds,
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

    app.state.minio_client = create_minio_client(settings.minio)

    app.state.jwt_public_key = load_public_key(settings.service.jwt_public_key_path)
    app.state.service_settings = settings.service

    scheduler_manager = await _build_workers(
        database.session_factory, cache.client, settings, events.manager.publish
    )
    app.state.scheduler_manager = scheduler_manager

    logger.info(
        "plugin-marketplace-service starting up",
        extra={
            "extra_fields": {
                "workers_enabled": settings.service.workers_enabled,
                "health_probe_sweep_seconds": settings.service.health_probe_sweep_seconds,
                "marketplace_approval_sweep_seconds": (
                    settings.service.marketplace_approval_sweep_seconds
                ),
                "statistics_rollup_seconds": settings.service.statistics_rollup_seconds,
                "review_moderation_sweep_seconds": settings.service.review_moderation_sweep_seconds,
            }
        },
    )
    try:
        yield
    finally:
        if scheduler_manager is not None:
            await scheduler_manager.stop()
        await database.shutdown()
        await cache.shutdown()
        await events.shutdown()
        logger.info("plugin-marketplace-service shutting down")


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    settings = get_settings()
    configure_logging(
        service=settings.application.app_name,
        environment=settings.application.environment,
        level=settings.application.log_level,
    )

    app = FastAPI(
        title="AI-IOS Enterprise Plugin Marketplace Service",
        description=(
            "Plugin registration, manifest validation, packaging and "
            "Ed25519 signing, dependency resolution, sandboxed "
            "execution, installation lifecycle, permissions, publisher "
            "trust, marketplace listings, reviews/ratings, and "
            "analytics/reports/audit. See this package's own README."
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

    for router in ALL_ROUTERS:
        app.include_router(router)

    Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=True)

    return app


def _build_cors_config(settings: Settings) -> CorsConfig:
    """Build the CORS policy for the current environment."""
    if settings.application.environment.value == "production":
        return production_cors_config(settings.service.cors_allowed_origins)
    return development_cors_config()


__all__ = ["create_app"]
