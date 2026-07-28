"""Application factory.

Assembles the FastAPI application: configuration, logging, database,
cache, events, notifications, object storage, JWT verification key,
middleware, exception handlers, routers, the scheduled-report worker,
and Prometheus instrumentation.

Unlike ``services/ai-assistant-service``, this service **does** register
a scheduler: unattended report runs are its whole reason for existing,
and leader election is what keeps a multi-replica deployment from
mailing the same report to everyone N times.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator
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
from shared_core.storage.client import create_minio_client
from shared_core.storage.wrapper import StorageWrapper
from shared_core.validation.middleware import RequestValidationMiddleware
from starlette.middleware.cors import CORSMiddleware

from app.api import delivery_router, health_router, reports_router, templates_router
from app.clients.platform import PlatformSourceClient, SourceEndpoints
from app.config.keys import load_public_key
from app.config.settings import ReportingServiceSettings, Settings, get_settings
from app.middleware.timing import TimingMiddleware
from app.notifications.report_notifications import ReportNotificationService
from app.scheduler.registrar import register_scheduled_report_tick
from app.workers.scheduler import ScheduledReportWorker

logger = get_logger("app.startup")


def _build_storage(settings: Settings) -> StorageWrapper | None:
    """Build the object-storage wrapper, or ``None`` if unconfigured.

    Object storage is one distribution channel among six. A deployment
    without MinIO credentials should start normally and report that
    channel unavailable, not fail to boot.
    """
    if not settings.minio.minio_access_key or not settings.minio.minio_secret_key:
        return None
    try:
        return StorageWrapper(create_minio_client(settings.minio))
    except Exception as exc:
        logger.warning(
            "Object storage is unavailable; that distribution channel is disabled.",
            extra={"extra_fields": {"error": str(exc)}},
        )
        return None


def _build_source_endpoints(settings: ReportingServiceSettings) -> SourceEndpoints:
    """Every data source's base URL, in one place."""
    return SourceEndpoints(
        inventory=settings.inventory_service_base_url,
        discovery=settings.discovery_service_base_url,
        configuration=settings.configuration_service_base_url,
        automation=settings.automation_service_base_url,
        workflow=settings.workflow_runtime_service_base_url,
        validation=settings.validation_service_base_url,
        monitoring=settings.monitoring_service_base_url,
        alerting=settings.alerting_service_base_url,
        ai_assistant=settings.ai_assistant_service_base_url,
        compliance=settings.compliance_service_base_url,
        incident=settings.incident_service_base_url,
        administration=settings.administration_service_base_url,
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
    app.state.storage = _build_storage(settings)
    app.state.jwt_public_key = load_public_key(settings.service.jwt_public_key_path)
    app.state.service_settings = settings.service

    app.state.http_client = httpx.AsyncClient(timeout=settings.service.http_client_timeout_seconds)

    scheduler_manager: SchedulerManager | None = None
    if settings.service.scheduler_enabled:
        queue = await create_queue_framework(settings.rabbitmq)
        scheduler_manager = create_scheduler_framework(
            queue.manager, cache.client, queue_name="reporting_scheduler_queue"
        )
        endpoints = _build_source_endpoints(settings.service)
        worker = ScheduledReportWorker(
            database.session_factory,
            source_client_factory=lambda: PlatformSourceClient(
                app.state.http_client,
                endpoints,
                caller_token=settings.service.scheduled_run_token,
                max_rows=settings.service.max_rows_per_report,
            ),
            publish_event=app.state.publish_event,
            notifications=ReportNotificationService(app.state.notification_manager),
        )
        register_scheduled_report_tick(
            scheduler_manager,
            worker.run_job,
            interval_seconds=settings.service.scheduler_poll_seconds,
        )
        await scheduler_manager.start()
    app.state.scheduler_manager = scheduler_manager

    logger.info(
        "reporting-service starting up",
        extra={
            "extra_fields": {
                "object_storage": app.state.storage is not None,
                "ai_reporting": settings.service.ai_reporting_enabled,
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
        await app.state.http_client.aclose()
        logger.info("reporting-service shutting down")


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    settings = get_settings()
    configure_logging(
        service=settings.application.app_name,
        environment=settings.application.environment,
        level=settings.application.log_level,
    )

    app = FastAPI(
        title="AI-IOS Reporting Service",
        description=(
            "Enterprise reporting platform -- report designer, rendering engine, "
            "scheduling, multi-format export (PDF/XLSX/CSV/JSON/Markdown/HTML/XML), "
            "distribution, immutable archive, AI summaries, and analytics."
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
    app.include_router(templates_router)
    app.include_router(delivery_router)
    app.include_router(reports_router)

    Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=True)

    return app


def _build_cors_config(settings: Settings) -> CorsConfig:
    """Build the CORS policy for the current environment."""
    if settings.application.environment.value == "production":
        return production_cors_config(settings.service.cors_allowed_origins)
    return development_cors_config()


__all__ = ["create_app"]
