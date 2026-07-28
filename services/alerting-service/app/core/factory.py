"""Application factory.

Assembles the FastAPI application: configuration, logging, database,
cache, events, notifications, JWT verification key, middleware,
exception handlers, routers, Prometheus instrumentation, and the
recurring escalation scheduler. Kept separate from ``main.py`` so
tests can construct the app without starting a server. No Neo4j driver
-- docs/045 names no graph concept for this service.

**Scheduler registration is per-organization and lazy**, unlike
``services/monitoring-service``'s own per-collector registration: an
escalation pass is organization-scoped work driven by whatever alerts
happen to be open, so registering one recurring job per organization
that actually has an enabled escalation policy is both sufficient and
far cheaper than one job per alert.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

import httpx
from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator
from shared_core.cache.factory import create_cache_framework
from shared_core.cache.settings import CacheSettings
from shared_core.database.factory import DatabaseFramework, create_database_framework
from shared_core.database.session import session_scope
from shared_core.events.factory import create_event_framework
from shared_core.exceptions import register_exception_handlers
from shared_core.logging import configure_logging, get_logger
from shared_core.middleware import (
    LocalizationMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)
from shared_core.notifications.factory import create_notification_framework
from shared_core.notifications.manager import NotificationManager
from shared_core.queue.factory import create_queue_framework
from shared_core.scheduler import SchedulerManager, create_scheduler_framework
from shared_core.security.cors import CorsConfig, development_cors_config, production_cors_config
from shared_core.validation.middleware import RequestValidationMiddleware
from starlette.middleware.cors import CORSMiddleware

from app.api import (
    alerts_router,
    escalation_router,
    health_router,
    maintenance_windows_router,
    oncall_schedules_router,
    reports_router,
    routes_router,
    rules_router,
    statistics_router,
    suppression_router,
)
from app.config.keys import load_public_key
from app.config.settings import Settings, get_settings
from app.middleware.timing import TimingMiddleware
from app.repositories.alert_escalation import AlertEscalationPolicyRepository
from app.scheduling.registrar import register_escalation_pass
from app.types import EventPublisher
from app.workers.escalation_worker import build_escalation_job_fn

logger = get_logger("app.startup")


async def _register_escalation_jobs(
    scheduler_manager: SchedulerManager,
    database: DatabaseFramework,
    manager: NotificationManager,
    publish_event: EventPublisher,
    *,
    interval_seconds: float,
) -> None:
    """Register one recurring escalation pass per organization with a policy."""
    async with session_scope(database.session_factory) as session:
        policies = await AlertEscalationPolicyRepository(session).list_all_enabled()
    organization_ids: set[UUID] = {policy.organization_id for policy in policies}
    for organization_id in organization_ids:
        register_escalation_pass(
            scheduler_manager,
            organization_id,
            build_escalation_job_fn(organization_id, database, manager, publish_event),
            interval_seconds=interval_seconds,
        )


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

    queue = await create_queue_framework(settings.rabbitmq)

    scheduler_manager: SchedulerManager = create_scheduler_framework(
        queue.manager, cache.client, queue_name="alerting_scheduler_queue"
    )
    app.state.scheduler_manager = scheduler_manager
    await _register_escalation_jobs(
        scheduler_manager,
        database,
        app.state.notification_manager,
        app.state.publish_event,
        interval_seconds=settings.service.default_escalation_poll_interval_seconds,
    )
    await scheduler_manager.start()

    logger.info("alerting-service starting up")
    try:
        yield
    finally:
        await scheduler_manager.stop()
        await database.shutdown()
        await cache.shutdown()
        await events.shutdown()
        await queue.shutdown()
        await app.state.http_client.aclose()
        logger.info("alerting-service shutting down")


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    settings = get_settings()
    configure_logging(
        service=settings.application.app_name,
        environment=settings.application.environment,
        level=settings.application.log_level,
    )

    app = FastAPI(
        title="AI-IOS Alerting Service",
        description=(
            "Enterprise alerting service -- detects, correlates, deduplicates, suppresses, "
            "routes, escalates, tracks, and resolves operational alerts across Monitoring, "
            "Validation, Automation, Workflow Runtime, Configuration Management, Discovery, "
            "and Inventory."
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
    app.include_router(alerts_router)
    app.include_router(rules_router)
    app.include_router(maintenance_windows_router)
    app.include_router(oncall_schedules_router)
    app.include_router(statistics_router)
    app.include_router(reports_router)
    app.include_router(routes_router)
    app.include_router(escalation_router)
    app.include_router(suppression_router)

    Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=True)

    return app


def _build_cors_config(settings: Settings) -> CorsConfig:
    """Build the CORS policy for the current environment."""
    if settings.application.environment.value == "production":
        return production_cors_config(settings.service.cors_allowed_origins)
    return development_cors_config()


__all__ = ["create_app"]
