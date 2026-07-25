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
from shared_core.events.manager import EventManager
from shared_core.exceptions import register_exception_handlers
from shared_core.logging import configure_logging, get_logger
from shared_core.middleware import (
    LocalizationMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)
from shared_core.notifications.factory import create_notification_framework
from shared_core.notifications.manager import NotificationManager
from shared_core.queue.decorators import register_jobs
from shared_core.queue.factory import create_queue_framework
from shared_core.security.cors import CorsConfig, development_cors_config, production_cors_config
from shared_core.storage import StorageWrapper, create_minio_client
from shared_core.validation.middleware import RequestValidationMiddleware
from starlette.middleware.cors import CORSMiddleware

from app.api import (
    activity_router,
    address_router,
    avatar_router,
    contact_router,
    export_router,
    health_router,
    import_router,
    invitation_router,
    metadata_router,
    note_router,
    preferences_router,
    profile_router,
    settings_router,
    tag_router,
    user_router,
)
from app.config.keys import load_public_key
from app.config.settings import Settings, get_settings
from app.middleware.timing import TimingMiddleware
from app.notifications.user_notifications import UserNotificationService
from app.repositories.activity import UserActivityRepository
from app.repositories.export_job import UserExportJobRepository
from app.repositories.import_job import UserImportJobRepository
from app.repositories.user import UserRepository
from app.services.activity import UserActivityService
from app.services.export_service import UserExportService
from app.services.import_service import UserImportService
from app.services.user import UserService
from app.workers.export_worker import EXPORT_QUEUE_NAME, build_export_worker
from app.workers.import_worker import IMPORT_QUEUE_NAME, build_import_worker

logger = get_logger("app.startup")


@asynccontextmanager
async def _build_import_service(
    database: DatabaseFramework,
    events: EventManager,
    notification_manager: NotificationManager,
    minio_client: Minio,
    bucket: str,
) -> AsyncIterator[UserImportService]:
    """Assemble a :class:`UserImportService` scoped to one commit-or-rollback
    unit of work (see :func:`app.workers.import_worker.build_import_worker`'s
    docstring for the real bug -- a job silently never committing -- this
    ``session_scope`` wrapping was added to fix). The Minio client itself is
    process-wide (its own internal connection pool), reused rather than
    rebuilt per job.
    """
    async with session_scope(database.session_factory) as session:
        activity = UserActivityService(UserActivityRepository(session))
        notifications = UserNotificationService(notification_manager)
        users = UserService(
            UserRepository(session), activity, notifications, publish_event=events.publish
        )
        storage = StorageWrapper(minio_client)
        yield UserImportService(
            UserImportJobRepository(session),
            users,
            activity,
            storage,
            bucket=bucket,
            publish_event=events.publish,
        )


@asynccontextmanager
async def _build_export_service(
    database: DatabaseFramework, events: EventManager, minio_client: Minio, bucket: str
) -> AsyncIterator[UserExportService]:
    """Assemble a :class:`UserExportService` scoped to one commit-or-rollback
    unit of work -- see :func:`_build_import_service`'s docstring.
    """
    async with session_scope(database.session_factory) as session:
        activity = UserActivityService(UserActivityRepository(session))
        storage = StorageWrapper(minio_client)
        yield UserExportService(
            UserExportJobRepository(session),
            UserRepository(session),
            activity,
            storage,
            bucket=bucket,
            publish_event=events.publish,
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

    queue = await create_queue_framework(settings.rabbitmq)
    app.state.queue_producer = queue.producer
    # A consumer can only subscribe to a queue that already exists --
    # shared_core.queue.consumer.Consumer.subscribe() passively looks the
    # queue up rather than declaring it, per shared_core.queue.manager
    # .QueueManager.consume()'s own implementation. Declare both queues
    # (with their dead-letter queues) before registering any handler.
    await queue.manager.declare_queue_with_dlq(IMPORT_QUEUE_NAME)
    await queue.manager.declare_queue_with_dlq(EXPORT_QUEUE_NAME)

    def _import_service_factory() -> AbstractAsyncContextManager[UserImportService]:
        return _build_import_service(
            database,
            events.manager,
            app.state.notification_manager,
            app.state.minio_client,
            settings.service.import_export_bucket,
        )

    def _export_service_factory() -> AbstractAsyncContextManager[UserExportService]:
        return _build_export_service(
            database, events.manager, app.state.minio_client, settings.service.import_export_bucket
        )

    await register_jobs(
        queue.consumer,
        [
            build_import_worker(_import_service_factory),
            build_export_worker(_export_service_factory),
        ],
    )

    logger.info("user-management-service starting up")
    try:
        yield
    finally:
        await database.shutdown()
        await cache.shutdown()
        await events.shutdown()
        await queue.shutdown()
        logger.info("user-management-service shutting down")


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    settings = get_settings()
    configure_logging(
        service=settings.application.app_name,
        environment=settings.application.environment,
        level=settings.application.log_level,
    )

    app = FastAPI(
        title="AI-IOS User Management Service",
        description="User profiles, lifecycle, invitations, and import/export across AI-IOS.",
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
    # single-segment literal path under /users/... (e.g. /users/profile,
    # /users/tags) MUST be registered before user_router's catch-all
    # /users/{user_id}, or it gets swallowed as a (UUID-invalid) user_id
    # path parameter instead of reaching its own router. Verified live:
    # this exact bug was caught via smoke-testing before this ordering
    # was fixed (GET /users/profile returned a 400 UUID-validation error).
    app.include_router(health_router)
    app.include_router(profile_router)
    app.include_router(preferences_router)
    app.include_router(settings_router)
    app.include_router(address_router)
    app.include_router(contact_router)
    app.include_router(metadata_router)
    app.include_router(avatar_router)
    app.include_router(tag_router)
    app.include_router(note_router)
    app.include_router(invitation_router)
    app.include_router(import_router)
    app.include_router(export_router)
    app.include_router(activity_router)
    app.include_router(user_router)

    Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=True)

    return app


def _build_cors_config(settings: Settings) -> CorsConfig:
    """Build the CORS policy for the current environment."""
    if settings.application.environment.value == "production":
        return production_cors_config(settings.service.cors_allowed_origins)
    return development_cors_config()


__all__ = ["create_app"]
