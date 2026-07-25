"""Application factory.

Assembles the FastAPI application: configuration, logging, database,
cache, events, queue (background discovery-job execution), a shared
HTTP client (Secrets Management Service credential resolution,
Inventory Service synchronization), the live
:class:`~shared_core.scheduler.SchedulerManager` (registering every
already-active :class:`~app.models.discovery_schedule.DiscoverySchedule`
on startup), notifications, JWT verification key, middleware, exception
handlers, routers, and Prometheus instrumentation. Kept separate from
``main.py`` so tests can construct the app without starting a server.

Unlike ``services/inventory-service``, this factory never opens a Neo4j
driver or MinIO client of its own -- see ``app/config/settings.py``'s
own module docstring for why.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID

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
from shared_core.queue.producer import Producer
from shared_core.scheduler import Job, JobFn, SchedulerManager, create_scheduler_framework
from shared_core.security.cors import CorsConfig, development_cors_config, production_cors_config
from shared_core.types.queue import QueueMessage
from shared_core.validation.middleware import RequestValidationMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.cors import CORSMiddleware

from app.api import (
    health_router,
    job_router,
    profile_router,
    result_router,
    scan_router,
    schedule_router,
    statistics_router,
)
from app.config.keys import load_public_key
from app.config.settings import DiscoveryServiceSettings, Settings, get_settings
from app.discovery.credentials import CredentialResolver
from app.discovery.inventory_sync import InventorySyncClient
from app.events.discovery_events import DiscoveryScheduleTriggeredEvent
from app.middleware.timing import TimingMiddleware
from app.models.enums import DiscoveryMode
from app.repositories.discovery_asset import DiscoveryAssetRepository
from app.repositories.discovery_audit import DiscoveryAuditRepository
from app.repositories.discovery_classification import DiscoveryClassificationRepository
from app.repositories.discovery_credential import DiscoveryCredentialRepository
from app.repositories.discovery_failure import DiscoveryFailureRepository
from app.repositories.discovery_history import DiscoveryHistoryRepository
from app.repositories.discovery_job import DiscoveryJobRepository
from app.repositories.discovery_relationship import DiscoveryRelationshipRepository
from app.repositories.discovery_result import DiscoveryResultRepository
from app.repositories.discovery_rule import DiscoveryRuleRepository
from app.repositories.discovery_schedule import DiscoveryScheduleRepository
from app.repositories.discovery_target import DiscoveryTargetRepository
from app.scheduling.registrar import register_schedule
from app.services.asset import DiscoveryAssetService
from app.services.audit import DiscoveryAuditService
from app.services.classification import DiscoveryClassificationService
from app.services.credential import DiscoveryCredentialService
from app.services.discovery_execution import DiscoveryExecutionService
from app.services.failure import DiscoveryFailureService
from app.services.history import DiscoveryHistoryService
from app.services.job import DiscoveryJobService
from app.services.relationship import DiscoveryRelationshipService
from app.services.result import DiscoveryResultService
from app.services.rule import DiscoveryRuleService
from app.services.schedule import DiscoveryScheduleService
from app.services.target import DiscoveryTargetService
from app.workers.discovery_worker import DISCOVERY_QUEUE_NAME, build_discovery_worker

logger = get_logger("app.startup")

EventPublisher = Callable[[DomainEvent], Awaitable[None]]
_SOURCE_SERVICE = "discovery-service"


def _build_execution_service(
    session: AsyncSession,
    http_client: httpx.AsyncClient,
    settings: DiscoveryServiceSettings,
    publish_event: EventPublisher | None,
) -> DiscoveryExecutionService:
    """Assemble a :class:`DiscoveryExecutionService` and every service it
    depends on, all bound to *session* -- shared by
    :func:`_build_discovery_execution_service` (the worker's own
    session-scoped factory) so it wires up the exact same dependency
    graph ``app/api/deps.py::get_execution_service`` builds per-request.
    """
    credential_resolver = CredentialResolver(
        http_client, base_url=settings.secrets_service_base_url
    )
    inventory_sync = InventorySyncClient(http_client, base_url=settings.inventory_service_base_url)
    return DiscoveryExecutionService(
        DiscoveryJobService(
            DiscoveryJobRepository(session),
            DiscoveryTargetRepository(session),
            session,
            publish_event=publish_event,
        ),
        DiscoveryTargetService(DiscoveryTargetRepository(session)),
        DiscoveryCredentialService(DiscoveryCredentialRepository(session)),
        DiscoveryResultService(DiscoveryResultRepository(session)),
        DiscoveryAssetService(
            DiscoveryAssetRepository(session), inventory_sync, publish_event=publish_event
        ),
        DiscoveryRelationshipService(
            DiscoveryRelationshipRepository(session), inventory_sync, publish_event=publish_event
        ),
        DiscoveryFailureService(DiscoveryFailureRepository(session)),
        DiscoveryHistoryService(DiscoveryHistoryRepository(session)),
        DiscoveryAuditService(DiscoveryAuditRepository(session)),
        credential_resolver,
        DiscoveryRuleService(DiscoveryRuleRepository(session)),
        DiscoveryClassificationService(DiscoveryClassificationRepository(session)),
        publish_event=publish_event,
    )


@asynccontextmanager
async def _build_discovery_execution_service(
    database: DatabaseFramework,
    http_client: httpx.AsyncClient,
    settings: DiscoveryServiceSettings,
    publish_event: EventPublisher | None,
) -> AsyncIterator[DiscoveryExecutionService]:
    """Assemble a :class:`DiscoveryExecutionService` scoped to one
    commit-or-rollback unit of work -- see
    ``services/inventory-service``'s identical ``_build_import_service``
    docstring for the real cross-session-visibility bug this
    ``session_scope`` wrapping was already caught and fixed for.
    """
    async with session_scope(database.session_factory) as session:
        yield _build_execution_service(session, http_client, settings, publish_event)


def _build_schedule_trigger_fn(
    database: DatabaseFramework, producer: Producer, publish_event: EventPublisher | None
) -> JobFn:
    """Build the callback every registered
    :class:`~app.models.discovery_schedule.DiscoverySchedule` fires when
    due: creates a new :class:`~app.models.discovery_job.DiscoveryJob`
    against the schedule's ``profile_id`` and queues it for execution,
    the same fast-create/queue-consumed-execute split every interactive
    ``POST /discovery/*`` endpoint uses.

    The resulting queue message carries no ``caller_token`` -- a
    schedule fires with no live HTTP request behind it, so there is no
    caller identity to forward. See
    ``app/services/discovery_execution.py``'s own module docstring for
    the documented, honest limitation this produces.
    """

    async def _fn(job: Job) -> None:
        schedule_id = UUID(str(job.metadata["discovery_schedule_id"]))
        profile_id = UUID(str(job.metadata["profile_id"]))
        async with session_scope(database.session_factory) as session:
            schedules = DiscoveryScheduleService(DiscoveryScheduleRepository(session))
            jobs = DiscoveryJobService(
                DiscoveryJobRepository(session),
                DiscoveryTargetRepository(session),
                session,
                publish_event=publish_event,
            )
            schedule = await schedules.get_by_id(schedule_id)
            discovery_job = await jobs.create_job(
                organization_id=schedule.organization_id,
                profile_id=profile_id,
                mode=DiscoveryMode.SCHEDULED,
                triggered_by=None,
                schedule_id=schedule_id,
            )
            await schedules.record_run(schedule_id, ran_at=datetime.now(UTC))

        message: QueueMessage = {"job_id": str(discovery_job.id)}
        await producer.publish(DISCOVERY_QUEUE_NAME, message)
        if publish_event is not None:
            await publish_event(
                DiscoveryScheduleTriggeredEvent(
                    source_service=_SOURCE_SERVICE,
                    organization_id=schedule.organization_id,
                    payload={"schedule_id": str(schedule_id), "job_id": str(discovery_job.id)},
                )
            )

    return _fn


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

    app.state.http_client = httpx.AsyncClient(timeout=settings.service.http_client_timeout_seconds)

    app.state.jwt_public_key = load_public_key(settings.service.jwt_public_key_path)
    app.state.service_settings = settings.service

    queue = await create_queue_framework(settings.rabbitmq)
    app.state.queue_producer = queue.producer
    await queue.manager.declare_queue_with_dlq(DISCOVERY_QUEUE_NAME)

    def _execution_service_factory() -> AbstractAsyncContextManager[DiscoveryExecutionService]:
        return _build_discovery_execution_service(
            database, app.state.http_client, settings.service, app.state.publish_event
        )

    await register_jobs(queue.consumer, [build_discovery_worker(_execution_service_factory)])

    scheduler_manager: SchedulerManager = create_scheduler_framework(
        queue.manager, cache.client, queue_name="discovery_scheduler_queue"
    )
    app.state.scheduler_manager = scheduler_manager
    app.state.discovery_schedule_fn = _build_schedule_trigger_fn(
        database, queue.producer, app.state.publish_event
    )

    async with session_scope(database.session_factory) as session:
        active_schedules = await DiscoveryScheduleService(
            DiscoveryScheduleRepository(session)
        ).list_active()
        for discovery_schedule in active_schedules:
            register_schedule(
                scheduler_manager, discovery_schedule, app.state.discovery_schedule_fn
            )
    await scheduler_manager.start()

    logger.info("discovery-service starting up")
    try:
        yield
    finally:
        await scheduler_manager.stop()
        await database.shutdown()
        await cache.shutdown()
        await events.shutdown()
        await queue.shutdown()
        await app.state.http_client.aclose()
        logger.info("discovery-service shutting down")


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    settings = get_settings()
    configure_logging(
        service=settings.application.app_name,
        environment=settings.application.environment,
        level=settings.application.log_level,
    )

    app = FastAPI(
        title="AI-IOS Discovery Service",
        description=(
            "Automated discovery of hybrid, cloud, edge, industrial, and Kubernetes assets "
            "across 26 protocols, classifying and synchronizing findings into the Inventory "
            "Service."
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
    # here owns a distinct first path segment under /discovery/... --
    # /discovery/jobs/{id} can only ever collide with another route
    # nested under /discovery/jobs itself, never with a sibling like
    # /discovery/scan or /discovery/profiles -- so, like
    # services/inventory-service's own registration-order comment, no
    # particular order is load-bearing here. Still listed in a fixed,
    # deliberate order for readability.
    app.include_router(health_router)
    app.include_router(job_router)
    app.include_router(profile_router)
    app.include_router(schedule_router)
    app.include_router(scan_router)
    app.include_router(result_router)
    app.include_router(statistics_router)

    Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=True)

    return app


def _build_cors_config(settings: Settings) -> CorsConfig:
    """Build the CORS policy for the current environment."""
    if settings.application.environment.value == "production":
        return production_cors_config(settings.service.cors_allowed_origins)
    return development_cors_config()


__all__ = ["create_app"]
