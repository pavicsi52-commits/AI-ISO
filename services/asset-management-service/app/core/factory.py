"""Application factory.

Assembles the FastAPI application: configuration, logging, database,
cache, events, queue (background analytics/expiration sweep), Neo4j
driver, notifications, JWT verification key, middleware, exception
handlers, routers, and Prometheus instrumentation. Kept separate from
``main.py`` so tests can construct the app without starting a server.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

import httpx
from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator
from shared_core.cache.factory import create_cache_framework
from shared_core.cache.settings import CacheSettings
from shared_core.database.factory import DatabaseFramework, create_database_framework
from shared_core.database.session import session_scope
from shared_core.events.base import DomainEvent
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
from shared_core.validation.middleware import RequestValidationMiddleware
from starlette.middleware.cors import CORSMiddleware

from app.api import (
    analytics_router,
    asset_health_router,
    assignment_router,
    compliance_router,
    contract_router,
    cost_router,
    dependency_router,
    health_router,
    maintenance_router,
    managed_asset_router,
    report_router,
    risk_router,
    warranty_router,
)
from app.config.keys import load_public_key
from app.config.settings import Settings, get_settings
from app.dependencies.client import create_neo4j_driver
from app.middleware.timing import TimingMiddleware
from app.repositories.asset_contract import AssetContractRepository
from app.repositories.asset_cost import AssetCostRepository
from app.repositories.asset_maintenance import AssetMaintenanceRepository
from app.repositories.asset_statistics import AssetStatisticsRepository
from app.repositories.asset_vendor import AssetVendorRepository
from app.repositories.asset_warranty import AssetWarrantyRepository
from app.repositories.managed_asset import ManagedAssetRepository
from app.services.contract import ContractService
from app.services.statistics import AssetStatisticsService
from app.services.warranty import WarrantyService
from app.workers.sweep_worker import SWEEP_QUEUE_NAME, SweepServices, build_sweep_worker

logger = get_logger("app.startup")

EventPublisher = Callable[[DomainEvent], Awaitable[None]]


@asynccontextmanager
async def _build_sweep_services(
    database: DatabaseFramework, publish_event: EventPublisher | None
) -> AsyncIterator[SweepServices]:
    """Assemble the three services :func:`app.workers.sweep_worker
    .build_sweep_worker` needs, all bound to one commit-or-rollback
    session -- the same "session_scope per background job" shape
    ``services/inventory-service``'s own ``_build_import_service``
    established.
    """
    async with session_scope(database.session_factory) as session:
        statistics = AssetStatisticsService(
            AssetStatisticsRepository(session),
            ManagedAssetRepository(session),
            AssetCostRepository(session),
            AssetMaintenanceRepository(session),
            AssetVendorRepository(session),
        )
        warranty = WarrantyService(
            AssetWarrantyRepository(session),
            ManagedAssetRepository(session),
            publish_event=publish_event,
        )
        contract = ContractService(
            AssetContractRepository(session),
            AssetVendorRepository(session),
            publish_event=publish_event,
        )
        yield statistics, warranty, contract


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

    app.state.neo4j_driver = create_neo4j_driver(settings.neo4j)

    app.state.jwt_public_key = load_public_key(settings.service.jwt_public_key_path)
    app.state.service_settings = settings.service

    app.state.http_client = httpx.AsyncClient(timeout=settings.service.http_client_timeout_seconds)

    queue = await create_queue_framework(settings.rabbitmq)
    app.state.queue_producer = queue.producer
    await queue.manager.declare_queue_with_dlq(SWEEP_QUEUE_NAME)

    def _sweep_service_factory() -> AbstractAsyncContextManager[SweepServices]:
        return _build_sweep_services(database, app.state.publish_event)

    await register_jobs(queue.consumer, [build_sweep_worker(_sweep_service_factory)])

    logger.info("asset-management-service starting up")
    try:
        yield
    finally:
        await database.shutdown()
        await cache.shutdown()
        await events.shutdown()
        await queue.shutdown()
        await app.state.neo4j_driver.close()
        await app.state.http_client.aclose()
        logger.info("asset-management-service shutting down")


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    settings = get_settings()
    configure_logging(
        service=settings.application.app_name,
        environment=settings.application.environment,
        level=settings.application.log_level,
    )

    app = FastAPI(
        title="AI-IOS Asset Management Service",
        description=(
            "Enterprise asset governance -- operational lifecycle, ownership, warranty, "
            "contracts, maintenance, compliance, risk, cost, and dependency analysis for "
            "inventoried assets."
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
    # *shape*, not type -- ``GET /assets/{managed_asset_id}`` matches
    # any single path segment under /assets, including the literal
    # "analytics"/"reports" segments those two routers own, and would
    # fail their request with a 422 (invalid UUID) before ever falling
    # through to the correct route. Unlike
    # ``services/inventory-service``'s own note that its router order
    # is *not* load-bearing (every router there owns a distinct first
    # path segment), analytics_router/report_router MUST be registered
    # before managed_asset_router here.
    app.include_router(health_router)
    app.include_router(analytics_router)
    app.include_router(report_router)
    app.include_router(managed_asset_router)
    app.include_router(assignment_router)
    app.include_router(maintenance_router)
    app.include_router(contract_router)
    app.include_router(warranty_router)
    app.include_router(compliance_router)
    app.include_router(risk_router)
    app.include_router(cost_router)
    app.include_router(asset_health_router)
    app.include_router(dependency_router)

    Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=True)

    return app


def _build_cors_config(settings: Settings) -> CorsConfig:
    """Build the CORS policy for the current environment."""
    if settings.application.environment.value == "production":
        return production_cors_config(settings.service.cors_allowed_origins)
    return development_cors_config()


__all__ = ["create_app"]
