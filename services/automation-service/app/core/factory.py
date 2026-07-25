"""Application factory.

Assembles the FastAPI application: configuration, logging, database,
cache, events, queue (background execution dispatch worker),
notifications, JWT verification key, connector registry, middleware,
exception handlers, routers, and Prometheus instrumentation. Kept
separate from ``main.py`` so tests can construct the app without
starting a server. No Neo4j driver -- docs/040 names no graph concept
for this service.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager

import httpx
from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator
from shared_core.cache.factory import create_cache_framework
from shared_core.cache.settings import CacheSettings
from shared_core.connectors.manager import ConnectorManager
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
    executions_router,
    health_router,
    jobs_router,
    reports_router,
    statistics_router,
    templates_router,
)
from app.config.keys import load_public_key
from app.config.settings import Settings, get_settings
from app.connectors.registry import build_connector_registry
from app.middleware.timing import TimingMiddleware
from app.repositories.automation_execution import AutomationExecutionRepository
from app.repositories.automation_execution_log import AutomationExecutionLogRepository
from app.repositories.automation_execution_step import AutomationExecutionStepRepository
from app.repositories.automation_job import AutomationJobRepository
from app.repositories.automation_output import AutomationOutputRepository
from app.repositories.automation_result import AutomationResultRepository
from app.repositories.automation_retry_history import AutomationRetryHistoryRepository
from app.repositories.automation_target import AutomationTargetRepository
from app.secrets.credential_resolver import SecretCredentialResolver
from app.services.execution import AutomationExecutionService
from app.workers.execution_worker import EXECUTION_QUEUE_NAME, build_execution_worker

logger = get_logger("app.startup")


@asynccontextmanager
async def _build_execution_service(
    database: DatabaseFramework,
    connector_manager: ConnectorManager,
    http_client: httpx.AsyncClient,
    secrets_service_base_url: str,
    max_parallel_targets: int,
) -> AsyncIterator[AutomationExecutionService]:
    """Assemble the service :func:`app.workers.execution_worker
    .build_execution_worker` needs, bound to one commit-or-rollback
    session -- the same "session_scope per background job" shape
    ``services/configuration-management-service``'s own
    ``_build_statistics_service`` established.
    """
    async with session_scope(database.session_factory) as session:
        credentials = SecretCredentialResolver(http_client, base_url=secrets_service_base_url)
        yield AutomationExecutionService(
            AutomationExecutionRepository(session),
            AutomationExecutionStepRepository(session),
            AutomationExecutionLogRepository(session),
            AutomationOutputRepository(session),
            AutomationResultRepository(session),
            AutomationRetryHistoryRepository(session),
            AutomationJobRepository(session),
            AutomationTargetRepository(session),
            connector_manager,
            credentials,
            max_parallel_targets=max_parallel_targets,
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
    app.state.connector_manager = ConnectorManager(registry=build_connector_registry())

    queue = await create_queue_framework(settings.rabbitmq)
    app.state.queue_producer = queue.producer
    await queue.manager.declare_queue_with_dlq(EXECUTION_QUEUE_NAME)

    def _execution_service_factory() -> AbstractAsyncContextManager[AutomationExecutionService]:
        return _build_execution_service(
            database,
            app.state.connector_manager,
            app.state.http_client,
            settings.service.secrets_service_base_url,
            settings.service.max_parallel_targets,
        )

    await register_jobs(queue.consumer, [build_execution_worker(_execution_service_factory)])

    logger.info("automation-service starting up")
    try:
        yield
    finally:
        await database.shutdown()
        await cache.shutdown()
        await events.shutdown()
        await queue.shutdown()
        await app.state.http_client.aclose()
        logger.info("automation-service shutting down")


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    settings = get_settings()
    configure_logging(
        service=settings.application.app_name,
        environment=settings.application.environment,
        level=settings.application.log_level,
    )

    app = FastAPI(
        title="AI-IOS Automation Service",
        description=(
            "Enterprise automation -- playbooks, workflows, scripts, TOSCA deployments, "
            "configuration enforcement, validation execution, operational tasks, and "
            "scheduled jobs, dispatched against real infrastructure via SSH and local runners."
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

    # Every router here owns a distinct top-level path segment under
    # /automation/ (jobs, executions, templates, statistics, reports), so
    # unlike services/configuration-management-service's own
    # profile_router (whose /{id} catch-all collides with sibling literal
    # routes at the *same* path depth), registration order carries no
    # route-matching hazard here.
    app.include_router(health_router)
    app.include_router(jobs_router)
    app.include_router(executions_router)
    app.include_router(templates_router)
    app.include_router(statistics_router)
    app.include_router(reports_router)

    Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=True)

    return app


def _build_cors_config(settings: Settings) -> CorsConfig:
    """Build the CORS policy for the current environment."""
    if settings.application.environment.value == "production":
        return production_cors_config(settings.service.cors_allowed_origins)
    return development_cors_config()


__all__ = ["create_app"]
