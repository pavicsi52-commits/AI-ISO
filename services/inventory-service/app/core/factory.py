"""Application factory.

Assembles the FastAPI application: configuration, logging, database,
cache, events, queue (background import/export jobs), storage, Neo4j
driver, notifications, JWT verification key, middleware, exception
handlers, routers, and Prometheus instrumentation. Kept separate from
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
from shared_core.storage import StorageWrapper, create_minio_client
from shared_core.validation.middleware import RequestValidationMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.cors import CORSMiddleware

from app.api import (
    analytics_router,
    asset_router,
    export_router,
    group_router,
    health_router,
    import_router,
    relationship_router,
    search_router,
    statistics_router,
    topology_router,
)
from app.config.keys import load_public_key
from app.config.settings import Settings, get_settings
from app.middleware.timing import TimingMiddleware
from app.repositories.asset import AssetRepository
from app.repositories.asset_export_job import AssetExportJobRepository
from app.repositories.asset_health_history import AssetHealthHistoryRepository
from app.repositories.asset_history import AssetHistoryRepository
from app.repositories.asset_import_job import AssetImportJobRepository
from app.repositories.asset_lifecycle_history import AssetLifecycleHistoryRepository
from app.repositories.asset_status_history import AssetStatusHistoryRepository
from app.repositories.asset_tag import AssetTagRepository
from app.repositories.asset_topology_cache import AssetTopologyCacheRepository
from app.repositories.asset_version import AssetVersionRepository
from app.repositories.inventory_audit import InventoryAuditRepository
from app.services.asset import AssetService
from app.services.audit import InventoryAuditService
from app.services.export_service import AssetExportService
from app.services.health_history import AssetHealthHistoryService
from app.services.history import AssetHistoryService
from app.services.import_service import AssetImportService
from app.services.lifecycle_history import AssetLifecycleHistoryService
from app.services.status_history import AssetStatusHistoryService
from app.services.tag import AssetTagService
from app.services.topology import TopologyService
from app.services.version import AssetVersionService
from app.topology.client import create_neo4j_driver
from app.topology.graph import TopologyGraphClient
from app.workers.export_worker import EXPORT_QUEUE_NAME, build_export_worker
from app.workers.import_worker import IMPORT_QUEUE_NAME, build_import_worker

logger = get_logger("app.startup")


def _build_asset_service(session: AsyncSession, graph: TopologyGraphClient) -> AssetService:
    """Assemble an :class:`AssetService` and every service it depends on,
    all bound to *session* -- shared by :func:`_build_import_service` and
    :func:`_build_export_service` so both worker factories wire up the
    exact same dependency graph ``app/api/deps.py`` builds per-request.
    """
    return AssetService(
        AssetRepository(session),
        AssetVersionService(AssetVersionRepository(session)),
        AssetTagService(AssetTagRepository(session)),
        AssetStatusHistoryService(AssetStatusHistoryRepository(session)),
        AssetHealthHistoryService(AssetHealthHistoryRepository(session)),
        AssetLifecycleHistoryService(AssetLifecycleHistoryRepository(session)),
        AssetHistoryService(AssetHistoryRepository(session)),
        InventoryAuditService(InventoryAuditRepository(session)),
        TopologyService(graph, AssetTopologyCacheRepository(session)),
        publish_event=None,
    )


@asynccontextmanager
async def _build_import_service(
    database: DatabaseFramework, minio_client: Minio, graph: TopologyGraphClient, bucket: str
) -> AsyncIterator[AssetImportService]:
    """Assemble an :class:`AssetImportService` scoped to one
    commit-or-rollback unit of work -- see
    ``services/project-service``'s identical ``_build_import_service``
    docstring for the real cross-session-visibility bug this
    ``session_scope`` wrapping was already caught and fixed for.
    """
    async with session_scope(database.session_factory) as session:
        assets = _build_asset_service(session, graph)
        storage = StorageWrapper(minio_client)
        yield AssetImportService(
            AssetImportJobRepository(session), assets, storage, session, bucket=bucket
        )


@asynccontextmanager
async def _build_export_service(
    database: DatabaseFramework, minio_client: Minio, bucket: str
) -> AsyncIterator[AssetExportService]:
    """Assemble an :class:`AssetExportService` scoped to one
    commit-or-rollback unit of work -- see :func:`_build_import_service`'s
    docstring.
    """
    async with session_scope(database.session_factory) as session:
        storage = StorageWrapper(minio_client)
        yield AssetExportService(
            AssetExportJobRepository(session),
            AssetRepository(session),
            AssetTagRepository(session),
            storage,
            session,
            bucket=bucket,
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

    app.state.neo4j_driver = create_neo4j_driver(settings.neo4j)

    app.state.jwt_public_key = load_public_key(settings.service.jwt_public_key_path)
    app.state.service_settings = settings.service

    queue = await create_queue_framework(settings.rabbitmq)
    app.state.queue_producer = queue.producer
    # A consumer can only subscribe to a queue that already exists --
    # declare both queues (with their dead-letter queues) before
    # registering any handler, the same ordering
    # services/project-service's own lifespan requires.
    await queue.manager.declare_queue_with_dlq(IMPORT_QUEUE_NAME)
    await queue.manager.declare_queue_with_dlq(EXPORT_QUEUE_NAME)

    def _import_service_factory() -> AbstractAsyncContextManager[AssetImportService]:
        graph = TopologyGraphClient(app.state.neo4j_driver)
        return _build_import_service(
            database, app.state.minio_client, graph, settings.service.import_export_bucket
        )

    def _export_service_factory() -> AbstractAsyncContextManager[AssetExportService]:
        return _build_export_service(
            database, app.state.minio_client, settings.service.import_export_bucket
        )

    await register_jobs(
        queue.consumer,
        [
            build_import_worker(_import_service_factory),
            build_export_worker(_export_service_factory),
        ],
    )

    logger.info("inventory-service starting up")
    try:
        yield
    finally:
        await database.shutdown()
        await cache.shutdown()
        await events.shutdown()
        await queue.shutdown()
        await app.state.neo4j_driver.close()
        logger.info("inventory-service shutting down")


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    settings = get_settings()
    configure_logging(
        service=settings.application.app_name,
        environment=settings.application.environment,
        level=settings.application.log_level,
    )

    app = FastAPI(
        title="AI-IOS Inventory Service",
        description=(
            "Authoritative CMDB across hybrid, cloud, edge, industrial, and Kubernetes "
            "environments, with Neo4j-backed topology and relationship tracking."
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

    # FastAPI/Starlette match routes in registration order. Every router
    # here owns a distinct first path segment under /inventory/... --
    # /inventory/assets/{id} can only ever collide with another route
    # nested under /inventory/assets itself, never with a sibling like
    # /inventory/import or /inventory/groups -- so, unlike
    # services/project-service's own /projects/{id}-vs-/projects/import
    # collision (its catch-all sits directly under the shared /projects
    # prefix), no particular registration order is load-bearing here.
    # Routers are still listed in a fixed, deliberate order for
    # readability.
    app.include_router(health_router)
    app.include_router(asset_router)
    app.include_router(relationship_router)
    app.include_router(topology_router)
    app.include_router(group_router)
    app.include_router(import_router)
    app.include_router(export_router)
    app.include_router(search_router)
    app.include_router(statistics_router)
    app.include_router(analytics_router)

    Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=True)

    return app


def _build_cors_config(settings: Settings) -> CorsConfig:
    """Build the CORS policy for the current environment."""
    if settings.application.environment.value == "production":
        return production_cors_config(settings.service.cors_allowed_origins)
    return development_cors_config()


__all__ = ["create_app"]
