"""Application factory.

Assembles the FastAPI application: configuration, logging, database,
cache, events, notifications, JWT verification key, signing keypair,
middleware, exception handlers, routers, and Prometheus
instrumentation. Kept separate from ``main.py`` so tests can construct
the app without starting a server. No Neo4j driver, no queue workers --
docs/041 names no graph concept and no background-worker-shaped
capability (validation runs synchronously, inline, within each request)
for this service.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

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
from shared_core.security.cors import CorsConfig, development_cors_config, production_cors_config
from shared_core.validation.middleware import RequestValidationMiddleware
from starlette.middleware.cors import CORSMiddleware

from app.api import (
    health_router,
    playbooks_router,
    reports_router,
    repository_folders_router,
    search_router,
    statistics_router,
    templates_router,
)
from app.config.keys import load_public_key, load_signing_keypair
from app.config.settings import Settings, get_settings
from app.middleware.timing import TimingMiddleware

logger = get_logger("app.startup")


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
    app.state.signing_private_key, app.state.signing_public_key = load_signing_keypair(
        settings.service.signing_private_key_path, settings.service.signing_public_key_path
    )
    app.state.service_settings = settings.service

    logger.info("playbook-service starting up")
    try:
        yield
    finally:
        await database.shutdown()
        await cache.shutdown()
        await events.shutdown()
        logger.info("playbook-service shutting down")


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    settings = get_settings()
    configure_logging(
        service=settings.application.app_name,
        environment=settings.application.environment,
        level=settings.application.log_level,
    )

    app = FastAPI(
        title="AI-IOS Playbook Service",
        description=(
            "Enterprise playbook service -- a centralized automation content "
            "repository: storage, versioning, dependency resolution, structural "
            "validation, digital signatures, approval workflow, and distribution. "
            "Execution belongs to services/automation-service, not this service."
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
    # *shape*, not type -- ``GET /playbooks/{id}`` matches any single
    # path segment under /playbooks, including the literal "search"/
    # "templates"/"repository"/"statistics"/"reports" segments those
    # routers own, and would fail their request with a 422 (invalid
    # UUID) before ever falling through to the correct route.
    # search_router/templates_router/repository_folders_router/
    # statistics_router/reports_router MUST be registered before
    # playbooks_router, the same hazard
    # ``services/configuration-management-service``'s own
    # ``profile_router`` ordering note already documented.
    app.include_router(health_router)
    app.include_router(search_router)
    app.include_router(templates_router)
    app.include_router(repository_folders_router)
    app.include_router(statistics_router)
    app.include_router(reports_router)
    app.include_router(playbooks_router)

    Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=True)

    return app


def _build_cors_config(settings: Settings) -> CorsConfig:
    """Build the CORS policy for the current environment."""
    if settings.application.environment.value == "production":
        return production_cors_config(settings.service.cors_allowed_origins)
    return development_cors_config()


__all__ = ["create_app"]
