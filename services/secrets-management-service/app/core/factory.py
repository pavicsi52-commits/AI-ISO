"""Application factory.

Assembles the FastAPI application: configuration, logging, database,
cache, events, notifications, JWT verification key, envelope-encryption
master key, background expiry/lease-sweep workers, middleware,
exception handlers, routers, and Prometheus instrumentation. Kept
separate from ``main.py`` so tests can construct the app without
starting a server.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager

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
from shared_core.security.cors import CorsConfig, development_cors_config, production_cors_config
from shared_core.validation.middleware import RequestValidationMiddleware
from starlette.middleware.cors import CORSMiddleware

from app.api import (
    api_key_router,
    certificate_router,
    health_router,
    lease_router,
    provider_router,
    search_router,
    secret_router,
    ssh_key_router,
)
from app.config.keys import load_public_key
from app.config.master_key import load_master_key
from app.config.settings import Settings, get_settings
from app.encryption.envelope import EnvelopeEncryption
from app.middleware.timing import TimingMiddleware
from app.notifications.secret_notifications import SecretNotificationService
from app.repositories.certificate import CertificateRepository
from app.repositories.encryption_key import EncryptionKeyRepository
from app.repositories.key_rotation_history import KeyRotationHistoryRepository
from app.repositories.secret import SecretRepository
from app.repositories.secret_audit import SecretAuditRepository
from app.repositories.secret_lease import SecretLeaseRepository
from app.repositories.secret_rotation import SecretRotationRepository
from app.repositories.secret_tag import SecretTagRepository
from app.repositories.secret_version import SecretVersionRepository
from app.services.audit import SecretAuditService
from app.services.certificate import CertificateService
from app.services.encryption_key import EncryptionKeyService
from app.services.key_rotation_history import KeyRotationHistoryService
from app.services.lease import SecretLeaseService
from app.services.rotation_history import SecretRotationHistoryService
from app.services.secret import EventPublisher, SecretService
from app.services.secret_version import SecretVersionService
from app.services.tag import SecretTagService
from app.workers import (
    check_certificate_expirations,
    check_secret_expirations,
    run_periodic,
    sweep_expired_leases,
)

logger = get_logger("app.startup")


_WorkerServices = tuple[
    SecretService, CertificateService, SecretLeaseService, SecretNotificationService
]


@asynccontextmanager
async def _build_worker_services(
    database: DatabaseFramework,
    envelope: EnvelopeEncryption,
    notification_manager: NotificationManager,
    publish_event: EventPublisher | None,
) -> AsyncIterator[_WorkerServices]:
    """Assemble one commit-or-rollback unit of work's worth of services
    for the background workers, which run outside any HTTP request scope
    and so need their own session -- the same ``session_scope`` wrapping
    ``services/project-service``'s own ``_build_import_service`` uses.
    """
    async with session_scope(database.session_factory) as session:
        history = KeyRotationHistoryService(KeyRotationHistoryRepository(session))
        keys = EncryptionKeyService(
            EncryptionKeyRepository(session), envelope, history, publish_event=publish_event
        )
        versions = SecretVersionService(SecretVersionRepository(session), keys)
        tags = SecretTagService(SecretTagRepository(session))
        rotation_history = SecretRotationHistoryService(SecretRotationRepository(session))
        audit = SecretAuditService(SecretAuditRepository(session))
        secrets = SecretService(
            SecretRepository(session),
            versions,
            tags,
            rotation_history,
            audit,
            publish_event=publish_event,
        )
        certificates = CertificateService(
            CertificateRepository(session), secrets, publish_event=publish_event
        )
        leases = SecretLeaseService(
            SecretLeaseRepository(session), versions, publish_event=publish_event
        )
        notifications = SecretNotificationService(notification_manager)
        yield secrets, certificates, leases, notifications


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

    master_key = load_master_key(settings.service.master_key_path)
    app.state.envelope_encryption = EnvelopeEncryption(master_key)

    def _worker_services() -> AbstractAsyncContextManager[_WorkerServices]:
        return _build_worker_services(
            database,
            app.state.envelope_encryption,
            app.state.notification_manager,
            events.manager.publish,
        )

    async def _run_expiry_check() -> None:
        async with _worker_services() as (secrets, certificates, _leases, notifications):
            await check_secret_expirations(secrets, notifications)
            await check_certificate_expirations(certificates, secrets, notifications)

    async def _run_lease_sweep() -> None:
        async with _worker_services() as (secrets, _certificates, leases, notifications):
            await sweep_expired_leases(leases, secrets, notifications)

    background_tasks = [
        asyncio.create_task(
            run_periodic(
                "expiry_check", settings.service.rotation_check_interval_seconds, _run_expiry_check
            )
        ),
        asyncio.create_task(
            run_periodic(
                "lease_sweep", settings.service.lease_sweep_interval_seconds, _run_lease_sweep
            )
        ),
    ]

    logger.info("secrets-management-service starting up")
    try:
        yield
    finally:
        for task in background_tasks:
            task.cancel()
        await asyncio.gather(*background_tasks, return_exceptions=True)
        await database.shutdown()
        await cache.shutdown()
        await events.shutdown()
        logger.info("secrets-management-service shutting down")


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    settings = get_settings()
    configure_logging(
        service=settings.application.app_name,
        environment=settings.application.environment,
        level=settings.application.log_level,
    )

    app = FastAPI(
        title="AI-IOS Secrets Management Service",
        description=(
            "Centralized secret storage, envelope encryption, rotation, "
            "leasing, and audit across AI-IOS."
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

    # FastAPI/Starlette match routes in registration order -- the literal
    # /secrets/search path MUST be registered before secret_router's
    # catch-all /secrets/{secret_id}, or it gets swallowed as an invalid
    # path-parameter attempt, the same routing-collision class
    # ``services/project-service``'s own factory.py already documents.
    app.include_router(health_router)
    app.include_router(search_router)
    app.include_router(lease_router)
    app.include_router(certificate_router)
    app.include_router(ssh_key_router)
    app.include_router(api_key_router)
    app.include_router(provider_router)
    app.include_router(secret_router)

    Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=True)

    return app


def _build_cors_config(settings: Settings) -> CorsConfig:
    """Build the CORS policy for the current environment."""
    if settings.application.environment.value == "production":
        return production_cors_config(settings.service.cors_allowed_origins)
    return development_cors_config()


__all__ = ["create_app"]
