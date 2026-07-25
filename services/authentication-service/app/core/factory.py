"""Application factory.

Assembles the FastAPI application: configuration, logging, database,
cache, events, notifications, JWT keys, middleware, exception
handlers, routers, and Prometheus instrumentation. Kept separate from
``main.py`` so tests can construct the app without starting a server.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator
from shared_core.cache.factory import create_cache_framework
from shared_core.cache.settings import CacheSettings
from shared_core.constants.authentication import AuthConstants
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
from shared_core.security.sessions import SessionManager
from shared_core.validation.middleware import RequestValidationMiddleware
from starlette.middleware.cors import CORSMiddleware

from app.api import (
    apikeys_router,
    auth_router,
    devices_router,
    health_router,
    mfa_router,
    password_router,
    profile_router,
    sessions_router,
    verification_router,
)
from app.config.keys import load_or_generate_keypair
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
    app.state.redis_client = cache.client
    app.state.session_manager = SessionManager(
        cache.manager,
        idle_timeout_seconds=AuthConstants.SESSION_IDLE_TIMEOUT_SECONDS,
        absolute_timeout_seconds=AuthConstants.SESSION_ABSOLUTE_TIMEOUT_SECONDS,
        max_concurrent_sessions=AuthConstants.MAX_CONCURRENT_SESSIONS,
    )

    events = await create_event_framework(settings.rabbitmq)
    app.state.publish_event = events.manager.publish

    app.state.notification_manager = create_notification_framework(email_settings=settings.email)

    app.state.jwt_keypair = load_or_generate_keypair(
        settings.service.jwt_private_key_path, settings.service.jwt_public_key_path
    )

    logger.info("authentication-service starting up")
    try:
        yield
    finally:
        await database.shutdown()
        await cache.shutdown()
        await events.shutdown()
        logger.info("authentication-service shutting down")


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    settings = get_settings()
    configure_logging(
        service=settings.application.app_name,
        environment=settings.application.environment,
        level=settings.application.log_level,
    )

    app = FastAPI(
        title="AI-IOS Authentication Service",
        description="Identity verification and session management across AI-IOS.",
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
    app.include_router(auth_router)
    app.include_router(password_router)
    app.include_router(verification_router)
    app.include_router(mfa_router)
    app.include_router(profile_router)
    app.include_router(sessions_router)
    app.include_router(devices_router)
    app.include_router(apikeys_router)

    Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=True)

    return app


def _build_cors_config(settings: Settings) -> CorsConfig:
    """Build the CORS policy for the current environment.

    Per docs/017_Enterprise_Security_Framework.md.txt "CORS":
    "Environment Specific" -- production only allows the explicitly
    configured origin list (never a wildcard alongside credentials);
    every other environment gets the permissive development default.
    """
    if settings.application.environment.value == "production":
        return production_cors_config(settings.service.cors_allowed_origins)
    return development_cors_config()


__all__ = ["create_app"]
