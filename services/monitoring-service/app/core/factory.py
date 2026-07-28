"""Application factory.

Assembles the FastAPI application: configuration, logging, database,
cache, events, notifications, JWT verification key, middleware,
exception handlers, routers, Prometheus instrumentation, and the
recurring collector/synthetic-test scheduler. Kept separate from
``main.py`` so tests can construct the app without starting a server.
No Neo4j driver -- docs/044 names no graph concept for this service. No
queue-based execute-on-demand worker (unlike
``services/validation-service``'s own ``execution_worker``) -- every
collection run here is scheduler-triggered
(:mod:`app.workers.collection_worker`) on each collector/synthetic
test's own ``interval_seconds``, matching
``services/workflow-runtime-service``'s own ``CRON``/``RECURRING``
timer pattern more closely than validation's on-demand one.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

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
from shared_core.queue.factory import create_queue_framework
from shared_core.scheduler import SchedulerManager, create_scheduler_framework
from shared_core.security.cors import CorsConfig, development_cors_config, production_cors_config
from shared_core.validation.middleware import RequestValidationMiddleware
from starlette.middleware.cors import CORSMiddleware

from app.api import (
    availability_router,
    collectors_router,
    dependencies_router,
    health_router,
    history_router,
    metrics_router,
    monitoring_health_router,
    performance_router,
    reports_router,
    retention_router,
    rules_router,
    sla_router,
    slo_router,
    statistics_router,
    synthetic_tests_router,
    targets_router,
    thresholds_router,
)
from app.clients.automation_client import AutomationClient
from app.clients.configuration_client import ConfigurationClient
from app.clients.discovery_client import DiscoveryClient
from app.clients.inventory_client import InventoryClient
from app.clients.validation_client import ValidationClient
from app.clients.workflow_client import WorkflowRuntimeClient
from app.collectors.context import CollectorContext
from app.collectors.registry import CollectorRegistry
from app.config.keys import load_public_key
from app.config.settings import Settings, get_settings
from app.middleware.timing import TimingMiddleware
from app.repositories.monitoring_collector import MonitoringCollectorRepository
from app.repositories.monitoring_synthetic_test import MonitoringSyntheticTestRepository
from app.scheduling.registrar import register_collector, register_synthetic_test
from app.services.collection import EventPublisher
from app.workers.collection_worker import build_collector_job_fn, build_synthetic_test_job_fn

logger = get_logger("app.startup")

_NO_CALLER_TOKEN = ""
"""Scheduled collection runs have no human caller of their own -- no
service-account/machine-credential mechanism has been established by
any prior AI-IOS prompt, the same documented gap
``services/workflow-runtime-service``'s own scheduled-instance trigger
already accepts. Collectors that call another platform service
(``inventory_asset``/``configuration_drift``/``workflow_instance``/
``discovery_job``/``validation_posture``/``automation_job``) will
receive a 401 from that service until this gap is closed platform-wide;
every native collector (``connectivity``/``port``/``dns``/
``certificate``/``http``) is unaffected since it never calls another
AI-IOS service at all.
"""


def _build_collector_context(
    http_client: httpx.AsyncClient, settings: Settings
) -> CollectorContext:
    service = settings.service
    return CollectorContext(
        inventory=InventoryClient(
            http_client, base_url=service.inventory_service_base_url, caller_token=_NO_CALLER_TOKEN
        ),
        configuration=ConfigurationClient(
            http_client,
            base_url=service.configuration_service_base_url,
            caller_token=_NO_CALLER_TOKEN,
        ),
        automation=AutomationClient(
            http_client, base_url=service.automation_service_base_url, caller_token=_NO_CALLER_TOKEN
        ),
        workflow=WorkflowRuntimeClient(
            http_client,
            base_url=service.workflow_runtime_service_base_url,
            caller_token=_NO_CALLER_TOKEN,
        ),
        discovery=DiscoveryClient(
            http_client, base_url=service.discovery_service_base_url, caller_token=_NO_CALLER_TOKEN
        ),
        validation=ValidationClient(
            http_client, base_url=service.validation_service_base_url, caller_token=_NO_CALLER_TOKEN
        ),
    )


async def _register_scheduled_jobs(
    scheduler_manager: SchedulerManager,
    database: DatabaseFramework,
    registry: CollectorRegistry,
    context: CollectorContext,
    publish_event: EventPublisher,
) -> None:
    async with session_scope(database.session_factory) as session:
        collectors = await MonitoringCollectorRepository(session).list_all_active()
        synthetic_tests = await MonitoringSyntheticTestRepository(session).list_all_active()
    for collector in collectors:
        register_collector(
            scheduler_manager,
            collector,
            build_collector_job_fn(collector, database, registry, context, publish_event),
        )
    for test in synthetic_tests:
        register_synthetic_test(
            scheduler_manager,
            test,
            build_synthetic_test_job_fn(test, database, context, publish_event),
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
    app.state.collector_registry = CollectorRegistry()
    app.state.collector_context = _build_collector_context(app.state.http_client, settings)

    queue = await create_queue_framework(settings.rabbitmq)

    scheduler_manager: SchedulerManager = create_scheduler_framework(
        queue.manager, cache.client, queue_name="monitoring_scheduler_queue"
    )
    app.state.scheduler_manager = scheduler_manager
    await _register_scheduled_jobs(
        scheduler_manager,
        database,
        app.state.collector_registry,
        app.state.collector_context,
        app.state.publish_event,
    )
    await scheduler_manager.start()

    logger.info("monitoring-service starting up")
    try:
        yield
    finally:
        await scheduler_manager.stop()
        await database.shutdown()
        await cache.shutdown()
        await events.shutdown()
        await queue.shutdown()
        await app.state.http_client.aclose()
        logger.info("monitoring-service shutting down")


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    settings = get_settings()
    configure_logging(
        service=settings.application.app_name,
        environment=settings.application.environment,
        level=settings.application.log_level,
    )

    app = FastAPI(
        title="AI-IOS Monitoring Service",
        description=(
            "Enterprise monitoring and observability service -- distributed collectors, "
            "time-series metrics, health/availability/performance monitoring, synthetic "
            "checks, dependency-aware health, SLA/SLO tracking, analytics, and reporting "
            "across infrastructure, cloud, Kubernetes, applications, databases, and "
            "industrial systems."
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
    app.include_router(targets_router)
    app.include_router(metrics_router)
    app.include_router(monitoring_health_router)
    app.include_router(history_router)
    app.include_router(availability_router)
    app.include_router(performance_router)
    app.include_router(thresholds_router)
    app.include_router(sla_router)
    app.include_router(slo_router)
    app.include_router(reports_router)
    app.include_router(statistics_router)
    app.include_router(collectors_router)
    app.include_router(rules_router)
    app.include_router(dependencies_router)
    app.include_router(synthetic_tests_router)
    app.include_router(retention_router)

    Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=True)

    return app


def _build_cors_config(settings: Settings) -> CorsConfig:
    """Build the CORS policy for the current environment."""
    if settings.application.environment.value == "production":
        return production_cors_config(settings.service.cors_allowed_origins)
    return development_cors_config()


__all__ = ["create_app"]
