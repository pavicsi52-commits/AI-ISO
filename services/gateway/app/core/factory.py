"""Application factory.

Assembles the FastAPI application: configuration, logging, middleware,
exception handlers, routers, and Prometheus instrumentation. Kept separate
from ``main.py`` so tests can construct the app without starting a server.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator
from shared_core.exceptions import register_exception_handlers
from shared_core.logging import configure_logging, get_logger
from shared_core.middleware import (
    LocalizationMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)
from shared_core.security.cors import CorsConfig, development_cors_config, production_cors_config
from shared_core.validation.middleware import RequestValidationMiddleware
from starlette.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.config.settings import Settings, get_settings
from app.middleware.timing import TimingMiddleware

logger = get_logger("app.startup")


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("gateway starting up")
    yield
    logger.info("gateway shutting down")


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    settings = get_settings()
    configure_logging(
        service=settings.app_name,
        environment=settings.environment,
        level=settings.log_level,
    )

    app = FastAPI(
        title="AI-IOS Gateway",
        description="Platform entry point: routing, authentication, rate limiting, observability.",
        version=settings.app_version,
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

    Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=True)

    return app


def _build_cors_config(settings: Settings) -> CorsConfig:
    """Build the CORS policy for the current environment.

    Per docs/017_Enterprise_Security_Framework.md.txt "CORS":
    "Environment Specific" -- production only allows the explicitly
    configured origin list (never a wildcard alongside credentials);
    every other environment gets the permissive development default.
    """
    if settings.environment == "production":
        return production_cors_config(settings.cors_allowed_origins)
    return development_cors_config()
