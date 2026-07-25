"""Application factory.

Assembles the FastAPI application: configuration, logging, database,
cache, events, queue (background statistics recompute and Git
synchronization workers), notifications, JWT verification key,
middleware, exception handlers, routers, and Prometheus
instrumentation. Kept separate from ``main.py`` so tests can construct
the app without starting a server. No Neo4j driver, unlike
``services/asset-management-service`` -- docs/039 names no graph
concept for this service.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

import httpx
from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator
from shared_core.cache.factory import create_cache_framework
from shared_core.cache.settings import CacheSettings
from shared_core.database.factory import DatabaseFramework, create_database_framework
from shared_core.database.session import session_scope
from shared_core.events.base import DomainEvent
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
    analytics_router,
    compliance_router,
    drift_router,
    git_router,
    health_router,
    profile_router,
    report_router,
    template_router,
)
from app.config.keys import load_public_key
from app.config.settings import Settings, get_settings
from app.gitops.credentials import GitCredentialResolver
from app.middleware.timing import TimingMiddleware
from app.repositories.configuration_audit import ConfigurationAuditRepository
from app.repositories.configuration_change_set import ConfigurationChangeSetRepository
from app.repositories.configuration_compliance import ConfigurationComplianceRepository
from app.repositories.configuration_drift import ConfigurationDriftRepository
from app.repositories.configuration_git_repository import ConfigurationGitRepositoryRepository
from app.repositories.configuration_profile import ConfigurationProfileRepository
from app.repositories.configuration_rollback import ConfigurationRollbackRepository
from app.repositories.configuration_statistics import ConfigurationStatisticsRepository
from app.repositories.configuration_version import ConfigurationVersionRepository
from app.services.audit import ConfigurationAuditService
from app.services.gitops import ConfigurationGitOpsService
from app.services.profile import ConfigurationProfileService
from app.services.statistics import ConfigurationStatisticsService
from app.services.version import ConfigurationVersionService
from app.workers.git_sync_worker import (
    GIT_SYNC_QUEUE_NAME,
    GitSyncServices,
    build_git_sync_worker,
)
from app.workers.statistics_worker import STATISTICS_QUEUE_NAME, build_statistics_worker

logger = get_logger("app.startup")

EventPublisher = Callable[[DomainEvent], Awaitable[None]]


@asynccontextmanager
async def _build_statistics_service(
    database: DatabaseFramework,
) -> AsyncIterator[ConfigurationStatisticsService]:
    """Assemble the service :func:`app.workers.statistics_worker
    .build_statistics_worker` needs, bound to one commit-or-rollback
    session -- the same "session_scope per background job" shape
    ``services/asset-management-service``'s own ``_build_sweep_services``
    established.
    """
    async with session_scope(database.session_factory) as session:
        yield ConfigurationStatisticsService(
            ConfigurationStatisticsRepository(session),
            ConfigurationProfileRepository(session),
            ConfigurationVersionRepository(session),
            ConfigurationDriftRepository(session),
            ConfigurationComplianceRepository(session),
            ConfigurationRollbackRepository(session),
            ConfigurationChangeSetRepository(session),
        )


@asynccontextmanager
async def _build_git_sync_services(
    database: DatabaseFramework, http_client: httpx.AsyncClient, secrets_service_base_url: str
) -> AsyncIterator[GitSyncServices]:
    """Assemble the two services :func:`app.workers.git_sync_worker
    .build_git_sync_worker` needs, bound to one commit-or-rollback session.
    """
    async with session_scope(database.session_factory) as session:
        credentials = GitCredentialResolver(http_client, base_url=secrets_service_base_url)
        gitops = ConfigurationGitOpsService(
            ConfigurationGitRepositoryRepository(session), http_client, credentials
        )
        profiles = ConfigurationProfileService(
            ConfigurationProfileRepository(session),
            ConfigurationVersionService(ConfigurationVersionRepository(session)),
            ConfigurationAuditService(ConfigurationAuditRepository(session)),
        )
        yield gitops, profiles


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
    app.state.queue_producer = queue.producer
    await queue.manager.declare_queue_with_dlq(STATISTICS_QUEUE_NAME)
    await queue.manager.declare_queue_with_dlq(GIT_SYNC_QUEUE_NAME)

    def _statistics_service_factory() -> (
        AbstractAsyncContextManager[ConfigurationStatisticsService]
    ):
        return _build_statistics_service(database)

    def _git_sync_service_factory() -> AbstractAsyncContextManager[GitSyncServices]:
        return _build_git_sync_services(
            database, app.state.http_client, settings.service.secrets_service_base_url
        )

    await register_jobs(
        queue.consumer,
        [
            build_statistics_worker(_statistics_service_factory),
            build_git_sync_worker(_git_sync_service_factory),
        ],
    )

    logger.info("configuration-management-service starting up")
    try:
        yield
    finally:
        await database.shutdown()
        await cache.shutdown()
        await events.shutdown()
        await queue.shutdown()
        await app.state.http_client.aclose()
        logger.info("configuration-management-service shutting down")


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    settings = get_settings()
    configure_logging(
        service=settings.application.app_name,
        environment=settings.application.environment,
        level=settings.application.log_level,
    )

    app = FastAPI(
        title="AI-IOS Configuration Management Service",
        description=(
            "Enterprise configuration management -- desired-state configuration profiles, "
            "versioning, baselines, drift detection, compliance, backup/restore/rollback, "
            "and GitOps/TOSCA/Ansible/Kubernetes integration."
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

    # FastAPI/Starlette match routes in registration order against
    # *shape*, not type -- ``GET/PUT/PATCH/DELETE /configurations/{id}``
    # matches any single path segment under /configurations, including
    # the literal "drift"/"compliance"/"templates"/"git"/"analytics"/
    # "reports" segments those routers own, and would fail their request
    # with a 422 (invalid UUID) before ever falling through to the
    # correct route. drift_router/compliance_router/template_router/
    # git_router/analytics_router/report_router MUST be registered
    # before profile_router, the same hazard
    # ``services/asset-management-service``'s own ``managed_asset_router``
    # ordering note already documented.
    app.include_router(health_router)
    app.include_router(drift_router)
    app.include_router(compliance_router)
    app.include_router(template_router)
    app.include_router(git_router)
    app.include_router(analytics_router)
    app.include_router(report_router)
    app.include_router(profile_router)

    Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=True)

    return app


def _build_cors_config(settings: Settings) -> CorsConfig:
    """Build the CORS policy for the current environment."""
    if settings.application.environment.value == "production":
        return production_cors_config(settings.service.cors_allowed_origins)
    return development_cors_config()


__all__ = ["create_app"]
