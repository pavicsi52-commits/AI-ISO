"""Application factory.

Assembles the FastAPI application: configuration, logging, database,
cache, events, queue (background execution dispatch worker), the
collector registry, notifications, JWT verification key, middleware,
exception handlers, routers, and Prometheus instrumentation. Kept
separate from ``main.py`` so tests can construct the app without
starting a server. No Neo4j driver -- docs/043 names no graph concept
for this service. No cron/recurring scheduler -- unlike
``services/workflow-runtime-service``'s own explicit "TIMERS" section,
docs/043 names no timer concept for this service; every execution is
either interactively (API) triggered or triggered by another platform
service (workflow/automation), never this service's own clock.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager

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
from shared_core.queue.decorators import register_jobs
from shared_core.queue.factory import create_queue_framework
from shared_core.security.cors import CorsConfig, development_cors_config, production_cors_config
from shared_core.validation.middleware import RequestValidationMiddleware
from starlette.middleware.cors import CORSMiddleware

from app.api import (
    categories_router,
    checks_router,
    health_router,
    profiles_router,
    remediation_router,
    reports_router,
    results_router,
    rules_router,
    statistics_router,
    templates_router,
    validations_router,
)
from app.collectors.registry import CollectorRegistry
from app.config.keys import load_public_key
from app.config.settings import Settings, get_settings
from app.middleware.timing import TimingMiddleware
from app.repositories.validation_category import ValidationCategoryRepository
from app.repositories.validation_check import ValidationCheckRepository
from app.repositories.validation_execution import ValidationExecutionRepository
from app.repositories.validation_failure import ValidationFailureRepository
from app.repositories.validation_history import ValidationHistoryRepository
from app.repositories.validation_profile import ValidationProfileRepository
from app.repositories.validation_result import ValidationResultRepository
from app.repositories.validation_result_detail import ValidationResultDetailRepository
from app.repositories.validation_rule import ValidationRuleRepository
from app.repositories.validation_score import ValidationScoreRepository
from app.repositories.validation_target import ValidationTargetRepository
from app.services.execution import EventPublisher, ValidationExecutionService
from app.workers.execution_worker import EXECUTION_QUEUE_NAME, build_execution_worker

logger = get_logger("app.startup")


@asynccontextmanager
async def _build_execution_service(
    database: DatabaseFramework,
    http_client: httpx.AsyncClient,
    collectors: CollectorRegistry,
    publish_event: EventPublisher,
    settings: Settings,
) -> AsyncIterator[ValidationExecutionService]:
    """Assemble the service :func:`app.workers.execution_worker
    .build_execution_worker` needs, bound to one commit-or-rollback
    session -- the same "session_scope per background job" shape
    ``services/workflow-runtime-service``'s own
    ``_build_execution_service`` established.
    """
    async with session_scope(database.session_factory) as session:
        yield ValidationExecutionService(
            ValidationExecutionRepository(session),
            ValidationProfileRepository(session),
            ValidationCheckRepository(session),
            ValidationCategoryRepository(session),
            ValidationRuleRepository(session),
            ValidationTargetRepository(session),
            ValidationResultRepository(session),
            ValidationResultDetailRepository(session),
            ValidationFailureRepository(session),
            ValidationScoreRepository(session),
            ValidationHistoryRepository(session),
            http_client,
            collectors,
            inventory_base_url=settings.service.inventory_service_base_url,
            configuration_base_url=settings.service.configuration_service_base_url,
            automation_base_url=settings.service.automation_service_base_url,
            workflow_base_url=settings.service.workflow_runtime_service_base_url,
            discovery_base_url=settings.service.discovery_service_base_url,
            publish_event=publish_event,
            max_parallel_checks=settings.service.max_parallel_checks,
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

    queue = await create_queue_framework(settings.rabbitmq)
    app.state.queue_producer = queue.producer
    await queue.manager.declare_queue_with_dlq(EXECUTION_QUEUE_NAME)

    def _execution_service_factory() -> AbstractAsyncContextManager[ValidationExecutionService]:
        return _build_execution_service(
            database,
            app.state.http_client,
            app.state.collector_registry,
            app.state.publish_event,
            settings,
        )

    await register_jobs(queue.consumer, [build_execution_worker(_execution_service_factory)])

    logger.info("validation-service starting up")
    try:
        yield
    finally:
        await database.shutdown()
        await cache.shutdown()
        await events.shutdown()
        await queue.shutdown()
        await app.state.http_client.aclose()
        logger.info("validation-service shutting down")


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    settings = get_settings()
    configure_logging(
        service=settings.application.app_name,
        environment=settings.application.environment,
        level=settings.application.log_level,
    )

    app = FastAPI(
        title="AI-IOS Validation Service",
        description=(
            "Enterprise validation engine -- infrastructure readiness, operational health, "
            "configuration, compliance, connectivity, security, and deployment validation via "
            "reusable profiles, a rule engine, weighted scoring, and remediation."
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

    # Every router here owns a distinct top-level path segment
    # (/validations, /validation-profiles, /validation-templates,
    # /validation-results, /validation-categories, /validation-checks,
    # /validation-rules, /validation/statistics, /validation/reports,
    # /validation/remediation) -- docs/043's own singular-"validation"
    # vs. plural-"validations" naming keeps every prefix textually
    # distinct, so unlike services/configuration-management-service's
    # own profile_router, registration order carries no route-matching
    # hazard here.
    app.include_router(health_router)
    app.include_router(validations_router)
    app.include_router(profiles_router)
    app.include_router(templates_router)
    app.include_router(results_router)
    app.include_router(categories_router)
    app.include_router(checks_router)
    app.include_router(rules_router)
    app.include_router(statistics_router)
    app.include_router(reports_router)
    app.include_router(remediation_router)

    Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=True)

    return app


def _build_cors_config(settings: Settings) -> CorsConfig:
    """Build the CORS policy for the current environment."""
    if settings.application.environment.value == "production":
        return production_cors_config(settings.service.cors_allowed_origins)
    return development_cors_config()


__all__ = ["create_app"]
