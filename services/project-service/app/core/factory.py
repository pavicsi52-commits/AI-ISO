"""Application factory.

Assembles the FastAPI application: configuration, logging, database,
cache, events, queue (background import/export jobs), storage,
notifications, JWT verification key, middleware, exception handlers,
routers, and Prometheus instrumentation. Kept separate from
``main.py`` so tests can construct the app without starting a server.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from fastapi import FastAPI
from minio import Minio
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
from shared_core.storage import StorageWrapper, create_minio_client
from shared_core.validation.middleware import RequestValidationMiddleware
from starlette.middleware.cors import CORSMiddleware

from app.api import (
    export_router,
    health_router,
    import_router,
    project_analytics_router,
    project_member_router,
    project_router,
    project_settings_router,
    project_template_router,
    search_router,
)
from app.config.keys import load_public_key
from app.config.settings import Settings, get_settings
from app.middleware.timing import TimingMiddleware
from app.repositories.project import ProjectRepository
from app.repositories.project_activity import ProjectActivityRepository
from app.repositories.project_archive import ProjectArchiveRepository
from app.repositories.project_export_job import ProjectExportJobRepository
from app.repositories.project_import_job import ProjectImportJobRepository
from app.repositories.project_preferences import ProjectPreferencesRepository
from app.repositories.project_settings import ProjectSettingsRepository
from app.repositories.project_tag import ProjectTagRepository
from app.services.activity import ProjectActivityService
from app.services.archive import ProjectArchiveService
from app.services.export_service import ProjectExportService
from app.services.import_service import ProjectImportService
from app.services.project import ProjectService
from app.workers.export_worker import EXPORT_QUEUE_NAME, build_export_worker
from app.workers.import_worker import IMPORT_QUEUE_NAME, build_import_worker

logger = get_logger("app.startup")


@asynccontextmanager
async def _build_import_service(
    database: DatabaseFramework, minio_client: Minio, bucket: str
) -> AsyncIterator[ProjectImportService]:
    """Assemble a :class:`ProjectImportService` scoped to one
    commit-or-rollback unit of work -- see
    ``services/user-management-service``'s identical
    ``_build_import_service`` docstring for the real cross-session-
    visibility bug this ``session_scope`` wrapping was already caught
    and fixed for.
    """
    async with session_scope(database.session_factory) as session:
        activity = ProjectActivityService(ProjectActivityRepository(session))
        archives = ProjectArchiveService(ProjectArchiveRepository(session))
        projects = ProjectService(
            ProjectRepository(session),
            ProjectSettingsRepository(session),
            ProjectPreferencesRepository(session),
            activity,
            archives,
            publish_event=None,
        )
        storage = StorageWrapper(minio_client)
        yield ProjectImportService(
            ProjectImportJobRepository(session), projects, storage, session, bucket=bucket
        )


@asynccontextmanager
async def _build_export_service(
    database: DatabaseFramework, minio_client: Minio, bucket: str
) -> AsyncIterator[ProjectExportService]:
    """Assemble a :class:`ProjectExportService` scoped to one
    commit-or-rollback unit of work -- see :func:`_build_import_service`'s
    docstring.
    """
    async with session_scope(database.session_factory) as session:
        storage = StorageWrapper(minio_client)
        yield ProjectExportService(
            ProjectExportJobRepository(session),
            ProjectRepository(session),
            ProjectTagRepository(session),
            storage,
            session,
            bucket=bucket,
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

    app.state.minio_client = create_minio_client(settings.minio)

    app.state.jwt_public_key = load_public_key(settings.service.jwt_public_key_path)
    app.state.service_settings = settings.service

    queue = await create_queue_framework(settings.rabbitmq)
    app.state.queue_producer = queue.producer
    # A consumer can only subscribe to a queue that already exists --
    # declare both queues (with their dead-letter queues) before
    # registering any handler, the same ordering
    # services/user-management-service's own lifespan requires.
    await queue.manager.declare_queue_with_dlq(IMPORT_QUEUE_NAME)
    await queue.manager.declare_queue_with_dlq(EXPORT_QUEUE_NAME)

    def _import_service_factory() -> AbstractAsyncContextManager[ProjectImportService]:
        return _build_import_service(
            database, app.state.minio_client, settings.service.import_export_bucket
        )

    def _export_service_factory() -> AbstractAsyncContextManager[ProjectExportService]:
        return _build_export_service(
            database, app.state.minio_client, settings.service.import_export_bucket
        )

    await register_jobs(
        queue.consumer,
        [
            build_import_worker(_import_service_factory),
            build_export_worker(_export_service_factory),
        ],
    )

    logger.info("project-service starting up")
    try:
        yield
    finally:
        await database.shutdown()
        await cache.shutdown()
        await events.shutdown()
        await queue.shutdown()
        logger.info("project-service shutting down")


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    settings = get_settings()
    configure_logging(
        service=settings.application.app_name,
        environment=settings.application.environment,
        level=settings.application.log_level,
    )

    app = FastAPI(
        title="AI-IOS Project Service",
        description="Project lifecycle, membership, roles, templates, and analytics across AI-IOS.",
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

    # FastAPI/Starlette match routes in registration order -- every
    # single-segment literal path under /projects/... (/projects/import,
    # /projects/export, /projects/templates, /projects/search) MUST be
    # registered before project_router's catch-all /projects/{project_id},
    # or it gets swallowed as a (UUID-invalid) project_id path parameter
    # instead of reaching its own router -- the exact bug
    # services/user-management-service's own factory.py already caught
    # live for its identical /users/profile-vs-/users/{user_id} shape.
    app.include_router(health_router)
    app.include_router(import_router)
    app.include_router(export_router)
    app.include_router(project_template_router)
    app.include_router(search_router)
    app.include_router(project_member_router)
    app.include_router(project_settings_router)
    app.include_router(project_analytics_router)
    app.include_router(project_router)

    Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=True)

    return app


def _build_cors_config(settings: Settings) -> CorsConfig:
    """Build the CORS policy for the current environment."""
    if settings.application.environment.value == "production":
        return production_cors_config(settings.service.cors_allowed_origins)
    return development_cors_config()


__all__ = ["create_app"]
