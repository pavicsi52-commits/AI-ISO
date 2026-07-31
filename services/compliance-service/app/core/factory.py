"""Application factory.

Assembles the FastAPI application: configuration, logging, PostgreSQL,
Redis, events, notifications, the JWT verification key, middleware,
exception handlers, routers, the background workers, and Prometheus
instrumentation.

**Router order is load-bearing.** All three business routers mount under
``/compliance``, and several own literal segments -- ``/compliance/scores``,
``/compliance/findings/summary``, ``/compliance/exceptions/expiring`` --
that sit alongside parameterised siblings like
``/compliance/findings/{finding_id}``. FastAPI matches in registration
order, so a literal route registered after its parameterised sibling is
never reached: ``/compliance/findings/summary`` gets parsed as a finding
whose id is the word "summary" and answers 422. Within each router the
literal paths are declared first for the same reason.
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
    assessments_router,
    catalogue_router,
    governance_router,
    health_router,
)
from app.config.keys import load_public_key
from app.config.settings import Settings, get_settings
from app.middleware.timing import TimingMiddleware
from app.workers.maintenance import MaintenanceWorker
from app.workers.registrar import register_exception_sweep, register_scoring_rollup
from app.workers.statistics import StatisticsWorker

logger = get_logger("app.startup")


async def _build_scheduler(
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: Redis,
    settings: Settings,
) -> SchedulerManager | None:
    """Register and start the leader-elected background jobs.

    Both jobs are leader-elected because both are pure database work with
    no per-replica state: N replicas computing the same rollup would be N
    times the load for an identical result, and two concurrent sweeps of
    one organization would race on the same exception rows -- which for
    an expiry sweep means an exception could be expired twice and counted
    twice in the statistics that follow.
    """
    if not settings.service.scheduler_enabled:
        return None

    queue = await create_queue_framework(settings.rabbitmq)
    manager = create_scheduler_framework(
        queue.manager, redis_client, queue_name="compliance_scheduler_queue"
    )
    register_scoring_rollup(
        manager,
        StatisticsWorker(session_factory).run_job,
        interval_seconds=settings.service.scoring_rollup_seconds,
    )
    register_exception_sweep(
        manager,
        MaintenanceWorker(session_factory).run_job,
        interval_seconds=settings.service.exception_sweep_seconds,
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

    if settings.service.minimum_controls_for_score <= 1:
        # Announced at every start. With no floor, a framework whose
        # single assessed control passed reports 100% -- and that number
        # gets quoted in a board pack by somebody who has no way to know
        # it came from one control out of three hundred.
        logger.warning(
            "minimum_controls_for_score is %d, so a framework with a single assessed "
            "control can publish a 100%% score. Raise "
            "AIIOS_COMPLIANCE_SERVICE_MINIMUM_CONTROLS_FOR_SCORE unless this is "
            "deliberate.",
            settings.service.minimum_controls_for_score,
        )

    scheduler_manager = await _build_scheduler(database.session_factory, cache.client, settings)
    app.state.scheduler_manager = scheduler_manager

    logger.info(
        "compliance-service starting up",
        extra={
            "extra_fields": {
                "max_controls_per_assessment": settings.service.max_controls_per_assessment,
                "max_targets_per_control": settings.service.max_targets_per_control,
                "assessment_concurrency": settings.service.assessment_concurrency,
                "evidence_retention_days": settings.service.evidence_retention_days,
                "max_exception_days": settings.service.max_exception_days,
                "minimum_controls_for_score": settings.service.minimum_controls_for_score,
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
        logger.info("compliance-service shutting down")


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    settings = get_settings()
    configure_logging(
        service=settings.application.app_name,
        environment=settings.application.environment,
        level=settings.application.log_level,
    )

    app = FastAPI(
        title="AI-IOS Compliance Service",
        description=(
            "Enterprise compliance management -- continuous assessment against CIS, "
            "NIST 800-53, ISO 27001, IEC 62443, SOC 2 and custom frameworks; "
            "immutable content-hashed evidence; cross-framework control mapping; "
            "deduplicated findings; expiring exceptions with mandatory review; a "
            "derived-severity risk register; remediation that is only closed by a "
            "verifying re-assessment; weighted scoring reported beside its coverage; "
            "and an append-only audit trail."
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

    app.include_router(health_router)
    app.include_router(catalogue_router)
    app.include_router(assessments_router)
    app.include_router(governance_router)
    app.include_router(analytics_router)

    Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=True)

    return app


def _build_cors_config(settings: Settings) -> CorsConfig:
    """Build the CORS policy for the current environment."""
    if settings.application.environment.value == "production":
        return production_cors_config(settings.service.cors_allowed_origins)
    return development_cors_config()


__all__ = ["create_app"]
