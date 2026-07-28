"""Application factory.

Assembles the FastAPI application: configuration, logging, database,
cache, events, notifications, JWT verification key, the model provider
registry, middleware, exception handlers, routers, and Prometheus
instrumentation.

No scheduler here, unlike ``services/monitoring-service`` and
``services/alerting-service``: every operation this service performs is
request-driven. There is no recurring work to run, and registering an
idle scheduler would add real infrastructure (leader election,
heartbeats) for no behaviour.
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
from shared_core.security.cors import CorsConfig, development_cors_config, production_cors_config
from shared_core.validation.middleware import RequestValidationMiddleware
from starlette.middleware.cors import CORSMiddleware

from app.api import (
    agents_router,
    chat_router,
    health_router,
    insights_router,
    knowledge_router,
    prompts_router,
)
from app.clients.registry import ModelRegistry, build_model_clients
from app.config.keys import load_public_key
from app.config.settings import Settings, get_settings
from app.middleware.timing import TimingMiddleware
from app.models.enums import ModelProvider

logger = get_logger("app.startup")

_FALLBACK_CHAIN: tuple[ModelProvider, ...] = (
    ModelProvider.OLLAMA,
    ModelProvider.OPENAI,
    ModelProvider.ANTHROPIC,
)
"""Providers tried, in order, when the requested one fails.

Self-hosted first: it costs nothing and, in a deployment that runs it,
is the most likely to still be reachable when a hosted provider is
having an outage. Only *configured* providers are ever attempted, so an
entry here with no credential is skipped rather than failing.
"""


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
    app.state.model_registry = ModelRegistry(
        build_model_clients(app.state.http_client, settings.service),
        default_provider=ModelProvider(settings.service.default_provider),
        default_model=settings.service.default_model,
        fallback_providers=_FALLBACK_CHAIN,
    )

    logger.info(
        "ai-assistant-service starting up",
        extra={
            "extra_fields": {
                "configured_providers": [
                    str(provider) for provider in app.state.model_registry.available_providers
                ],
                "embedding_provider": settings.service.default_embedding_provider,
            }
        },
    )
    try:
        yield
    finally:
        await database.shutdown()
        await cache.shutdown()
        await events.shutdown()
        await app.state.http_client.aclose()
        logger.info("ai-assistant-service shutting down")


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    settings = get_settings()
    configure_logging(
        service=settings.application.app_name,
        environment=settings.application.environment,
        level=settings.application.log_level,
    )

    app = FastAPI(
        title="AI-IOS AI Assistant Service",
        description=(
            "Enterprise AI operations copilot -- multi-agent orchestration, "
            "retrieval-augmented generation over platform knowledge, permission-aware "
            "tool calling, prompt management, and multi-provider model management."
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
    app.include_router(chat_router)
    app.include_router(knowledge_router)
    app.include_router(agents_router)
    app.include_router(prompts_router)
    app.include_router(insights_router)

    Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=True)

    return app


def _build_cors_config(settings: Settings) -> CorsConfig:
    """Build the CORS policy for the current environment."""
    if settings.application.environment.value == "production":
        return production_cors_config(settings.service.cors_allowed_origins)
    return development_cors_config()


__all__ = ["create_app"]
