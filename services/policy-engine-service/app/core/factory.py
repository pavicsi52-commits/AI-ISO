"""Application factory.

Assembles the FastAPI application: configuration, logging, PostgreSQL,
Redis, events, notifications, the JWT verification key, middleware,
exception handlers, routers, the background workers, and Prometheus
instrumentation.

**Router order is load-bearing.** Both business routers mount under
``/policies``, and one owns literal segments (``/policies/decisions``,
``/policies/quotas``) while the other owns ``/policies/{policy_id}``.
FastAPI matches in registration order, so the literal-segment router goes
first -- otherwise ``/policies/decisions`` is parsed as a policy whose id
is the word "decisions" and answers 422 for a malformed UUID. See
:mod:`app.api.__init__`.

**A startup warning, not a failure, when this deployment fails open.**
``fail_closed=False`` means an evaluation error authorizes whatever was
asked, which is a legitimate choice for a few deployments and a
catastrophic default. Refusing to start would be wrong -- an operator who
set it meant it -- but so would starting silently.
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

from app.api import health_router, operations_router, policies_router
from app.config.keys import load_public_key
from app.config.settings import Settings, get_settings
from app.middleware.timing import TimingMiddleware
from app.workers.maintenance import MaintenanceWorker
from app.workers.registrar import register_approval_sweep, register_statistics_rollup
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
    one organization would race on the same rows.
    """
    if not settings.service.scheduler_enabled:
        return None

    queue = await create_queue_framework(settings.rabbitmq)
    manager = create_scheduler_framework(
        queue.manager, redis_client, queue_name="policy_engine_scheduler_queue"
    )
    register_statistics_rollup(
        manager,
        StatisticsWorker(session_factory).run_job,
        interval_seconds=settings.service.statistics_rollup_seconds,
    )
    register_approval_sweep(
        manager,
        MaintenanceWorker(session_factory, graph_settings=settings.service).run_job,
        interval_seconds=settings.service.approval_sweep_seconds,
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

    if not settings.service.fail_closed:
        # Announced loudly at every start. Failing open means a database
        # blip, a malformed stored policy, or an unreachable attribute
        # silently authorizes whatever was asked -- and unlike failing
        # closed, nothing about it looks wrong from the outside.
        logger.warning(
            "This deployment is configured to FAIL OPEN: an evaluation error will "
            "authorize the request rather than refuse it. Set "
            "AIIOS_POLICY_ENGINE_SERVICE_FAIL_CLOSED=true unless this is deliberate.",
        )
    if settings.service.default_effect_on_no_match != "deny":
        logger.warning(
            "The default effect for an unmatched request is %r rather than 'deny'. "
            "Anything no policy covers will be permitted.",
            settings.service.default_effect_on_no_match,
        )

    scheduler_manager = await _build_scheduler(database.session_factory, cache.client, settings)
    app.state.scheduler_manager = scheduler_manager

    logger.info(
        "policy-engine-service starting up",
        extra={
            "extra_fields": {
                "fail_closed": settings.service.fail_closed,
                "default_effect": settings.service.default_effect_on_no_match,
                "max_policies_per_evaluation": settings.service.max_policies_per_evaluation,
                "quota_enforcement": settings.service.quota_enforcement_enabled,
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
        logger.info("policy-engine-service shutting down")


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    settings = get_settings()
    configure_logging(
        service=settings.application.app_name,
        environment=settings.application.environment,
        level=settings.application.log_level,
    )

    app = FastAPI(
        title="AI-IOS Policy Engine Service",
        description=(
            "Enterprise Policy-as-Code engine -- RBAC and ABAC, context-aware "
            "authorization, approval and quota policies, compliance rules, "
            "policy versioning with rollback, what-if simulation and conflict "
            "detection, and a decision API every platform service calls before "
            "a protected operation."
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
    app.include_router(operations_router)
    app.include_router(policies_router)

    Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=True)

    return app


def _build_cors_config(settings: Settings) -> CorsConfig:
    """Build the CORS policy for the current environment."""
    if settings.application.environment.value == "production":
        return production_cors_config(settings.service.cors_allowed_origins)
    return development_cors_config()


__all__ = ["create_app"]
