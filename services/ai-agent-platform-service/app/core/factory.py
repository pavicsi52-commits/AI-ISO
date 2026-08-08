"""Application factory.

Assembles the FastAPI application: configuration, logging, PostgreSQL,
Redis, events, Neo4j, the model provider registry, the outbound HTTP
client, the JWT verification key, middleware, exception handlers,
routers, and Prometheus instrumentation.
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
from shared_core.security.cors import CorsConfig, development_cors_config, production_cors_config
from shared_core.validation.middleware import RequestValidationMiddleware
from starlette.middleware.cors import CORSMiddleware

from app.api import ALL_ROUTERS
from app.clients.registry import ModelRegistry, build_model_clients
from app.config.keys import load_public_key
from app.config.settings import Settings, get_settings
from app.graph.client import GraphClient, create_neo4j_driver
from app.models.enums import ModelProvider
from app.sandbox.policy import AgentSandboxPolicy

logger = get_logger("app.startup")


def _build_model_registry(http_client: httpx.AsyncClient, settings: Settings) -> ModelRegistry:
    clients = build_model_clients(http_client, settings.service)
    return ModelRegistry(
        clients,
        default_provider=ModelProvider(settings.service.default_provider),
        default_model=settings.service.default_model,
    )


def _build_graph_client(settings: Settings) -> tuple[object, GraphClient]:
    driver = create_neo4j_driver(
        settings.neo4j,
        enabled=settings.service.neo4j_enabled,
        max_pool_size=settings.service.neo4j_max_connection_pool_size,
        connection_timeout=settings.service.neo4j_connection_timeout_seconds,
    )
    graph_client = GraphClient(
        driver,
        database=settings.service.neo4j_database,
        max_records=settings.service.neo4j_max_records,
        timeout_seconds=settings.service.neo4j_query_timeout_seconds,
        enabled=settings.service.neo4j_enabled,
    )
    return driver, graph_client


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

    app.state.jwt_public_key = load_public_key(settings.service.jwt_public_key_path)
    app.state.service_settings = settings.service

    app.state.http_client = httpx.AsyncClient(timeout=settings.service.http_client_timeout_seconds)
    app.state.model_registry = _build_model_registry(app.state.http_client, settings)

    neo4j_driver, graph_client = _build_graph_client(settings)
    app.state.neo4j_driver = neo4j_driver
    app.state.graph_client = graph_client

    app.state.sandbox_policy = AgentSandboxPolicy(
        execution_timeout_seconds=settings.service.default_execution_timeout_seconds,
        memory_limit_mb=settings.service.default_memory_limit_mb,
    )

    logger.info(
        "ai-agent-platform-service starting up",
        extra={
            "extra_fields": {
                "available_model_providers": [
                    str(provider) for provider in app.state.model_registry.available_providers
                ],
                "neo4j_enabled": settings.service.neo4j_enabled,
                "guardrails_enabled": settings.service.guardrails_enabled,
            }
        },
    )
    try:
        yield
    finally:
        await app.state.http_client.aclose()
        if neo4j_driver is not None:
            await neo4j_driver.close()
        await database.shutdown()
        await cache.shutdown()
        await events.shutdown()
        logger.info("ai-agent-platform-service shutting down")


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    settings = get_settings()
    configure_logging(
        service=settings.application.app_name,
        environment=settings.application.environment,
        level=settings.application.log_level,
    )

    app = FastAPI(
        title="AI-IOS Enterprise AI Agent Platform Service",
        description=(
            "Multi-agent orchestration, LangGraph-style workflow "
            "execution, MCP client/server, multi-model routing, tool "
            "registry and execution, memory, reasoning modes, "
            "guardrails, sandboxing, evaluation/benchmarking, and "
            "human-in-the-loop approval. See this package's own README."
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
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(LocalizationMiddleware)
    app.add_middleware(RequestValidationMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)

    register_exception_handlers(app)

    for router in ALL_ROUTERS:
        app.include_router(router)

    Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=True)

    return app


def _build_cors_config(settings: Settings) -> CorsConfig:
    """Build the CORS policy for the current environment."""
    if settings.application.environment.value == "production":
        return production_cors_config(settings.service.cors_allowed_origins)
    return development_cors_config()


__all__ = ["create_app"]
