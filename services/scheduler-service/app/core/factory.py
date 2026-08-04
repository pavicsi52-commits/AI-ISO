"""Application factory.

Assembles the FastAPI application: configuration, logging, PostgreSQL,
Redis, events, notifications, the JWT verification key, middleware,
exception handlers, routers, the background workers, and Prometheus
instrumentation.

**No single top-level prefix covers every router** -- see
``app/api/__init__.py`` for why ``/scheduler/jobs``, ``/scheduler/executions``,
``/scheduler/failures``, ``/scheduler/maintenance``, ``/scheduler/holidays``,
``/scheduler/priorities``, ``/scheduler/statistics``, ``/scheduler/reports``,
and ``/scheduler/audit`` are each mounted at their own path under the
shared ``/scheduler`` namespace instead.
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
    executions_router,
    failures_router,
    health_router,
    holidays_router,
    jobs_router,
    maintenance_router,
    priorities_router,
)
from app.config.keys import load_public_key
from app.config.settings import Settings, get_settings
from app.workers.due_schedule_sweep import DueScheduleSweepWorker
from app.workers.maintenance_sweep import MaintenanceSweepWorker
from app.workers.registrar import (
    register_due_schedule_sweep,
    register_maintenance_sweep,
    register_retry_sweep,
    register_statistics_rollup,
)
from app.workers.retry_sweep import RetrySweepWorker
from app.workers.statistics import StatisticsWorker

logger = get_logger("app.startup")


async def _build_scheduler(
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: Redis,
    settings: Settings,
    publish_event: object,
) -> SchedulerManager | None:
    """Register and start the leader-elected background jobs.

    All four are leader-elected: each is pure database work with no
    per-replica state, so N replicas would be N times the load for an
    identical result -- and concurrent sweeps of one organization's due
    schedules or retries would race on the same rows.
    """
    if not settings.service.scheduler_enabled:
        return None

    queue = await create_queue_framework(settings.rabbitmq)
    manager = create_scheduler_framework(
        queue.manager, redis_client, queue_name="scheduler_service_scheduler_queue"
    )
    register_due_schedule_sweep(
        manager,
        DueScheduleSweepWorker(
            session_factory, lookahead_seconds=settings.service.due_schedule_lookahead_seconds
        ).run_job,
        interval_seconds=settings.service.due_schedule_sweep_seconds,
    )
    register_retry_sweep(
        manager,
        RetrySweepWorker(session_factory).run_job,
        interval_seconds=settings.service.retry_sweep_seconds,
    )
    register_statistics_rollup(
        manager,
        StatisticsWorker(
            session_factory, window_hours=settings.service.statistics_window_hours
        ).run_job,
        interval_seconds=settings.service.statistics_rollup_seconds,
    )
    register_maintenance_sweep(
        manager,
        MaintenanceSweepWorker(
            session_factory,
            interval_seconds=settings.service.maintenance_sweep_seconds,
            publish_event=publish_event,
        ).run_job,
        interval_seconds=settings.service.maintenance_sweep_seconds,
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

    scheduler_manager = await _build_scheduler(
        database.session_factory, cache.client, settings, events.manager.publish
    )
    app.state.scheduler_manager = scheduler_manager

    logger.info(
        "scheduler-service starting up",
        extra={
            "extra_fields": {
                "default_max_attempts": settings.service.default_max_attempts,
                "priority_escalation_after_minutes": (
                    settings.service.priority_escalation_after_minutes
                ),
                "max_dependency_depth": settings.service.max_dependency_depth,
                "due_schedule_sweep_seconds": settings.service.due_schedule_sweep_seconds,
                "scheduler_enabled": settings.service.scheduler_enabled,
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
        logger.info("scheduler-service shutting down")


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    settings = get_settings()
    configure_logging(
        service=settings.application.app_name,
        environment=settings.application.environment,
        level=settings.application.log_level,
    )

    app = FastAPI(
        title="AI-IOS Enterprise Scheduler Service",
        description=(
            "Distributed job scheduling -- cron, calendar, interval, "
            "one-time, event-driven, and dependency-driven triggers, "
            "priority-based dispatch with escalation, fixed/linear/"
            "exponential retry policies with a dead letter path, manual "
            "failure recovery, maintenance windows and holiday calendars "
            "that suppress and reshape dispatch, and rolled-up "
            "statistics, generated reports, and an append-only audit "
            "trail. Dispatches jobs; never performs their own work -- "
            "see this package's own README."
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

    app.include_router(health_router)
    app.include_router(jobs_router)
    app.include_router(executions_router)
    app.include_router(failures_router)
    app.include_router(maintenance_router)
    app.include_router(holidays_router)
    app.include_router(priorities_router)
    app.include_router(analytics_router)

    Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=True)

    return app


def _build_cors_config(settings: Settings) -> CorsConfig:
    """Build the CORS policy for the current environment."""
    if settings.application.environment.value == "production":
        return production_cors_config(settings.service.cors_allowed_origins)
    return development_cors_config()


__all__ = ["create_app"]
