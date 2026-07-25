"""Application factory.

Assembles the FastAPI application: configuration, logging, database,
cache, events, notifications, JWT verification key, middleware,
exception handlers, routers, and Prometheus instrumentation. Kept
separate from ``main.py`` so tests can construct the app without
starting a server.
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
    analytics_router,
    department_org_router,
    department_router,
    health_router,
    invitation_org_router,
    invitation_router,
    organization_branding_router,
    organization_license_router,
    organization_quota_router,
    organization_router,
    organization_settings_router,
    team_org_router,
    team_router,
)
from app.config.keys import load_public_key
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

    logger.info("organization-service starting up")
    try:
        yield
    finally:
        await database.shutdown()
        await cache.shutdown()
        await events.shutdown()
        logger.info("organization-service shutting down")


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    settings = get_settings()
    configure_logging(
        service=settings.application.app_name,
        environment=settings.application.environment,
        level=settings.application.log_level,
    )

    app = FastAPI(
        title="AI-IOS Organization Service",
        description=(
            "Multi-tenant organization, department, team, subscription, "
            "and quota management for AI-IOS."
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

    # Literal-path routers (/departments/{id}, /teams/{id},
    # /organizations/invite/{accept,reject}) are registered before the
    # /organizations/{organization_id}/... routers as a matter of the same
    # defensive convention every prior AI-IOS service established, even
    # though these particular routes don't actually collide (different
    # segment depths/literals throughout) -- see app/api/department.py's
    # and app/api/invitation.py's own docstrings.
    app.include_router(health_router)
    app.include_router(department_router)
    app.include_router(team_router)
    app.include_router(invitation_router)
    app.include_router(organization_settings_router)
    app.include_router(organization_branding_router)
    app.include_router(department_org_router)
    app.include_router(team_org_router)
    app.include_router(organization_license_router)
    app.include_router(organization_quota_router)
    app.include_router(invitation_org_router)
    app.include_router(analytics_router)
    app.include_router(organization_router)

    Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=True)

    return app


def _build_cors_config(settings: Settings) -> CorsConfig:
    """Build the CORS policy for the current environment."""
    if settings.application.environment.value == "production":
        return production_cors_config(settings.service.cors_allowed_origins)
    return development_cors_config()


__all__ = ["create_app"]
