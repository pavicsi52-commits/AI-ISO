"""Application factory.

Assembles the FastAPI application: configuration, logging, database,
cache, events, queue (background execution dispatch worker plus the
``shared_core.workflow`` ``QUEUE``-node task queue), the cron/recurring
timer scheduler, notifications, JWT verification key, middleware,
exception handlers, routers, and Prometheus instrumentation. Kept
separate from ``main.py`` so tests can construct the app without
starting a server. No Neo4j driver -- docs/042 names no graph concept
for this service.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from uuid import UUID

import httpx
from fastapi import FastAPI
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
from shared_core.queue.producer import Producer
from shared_core.scheduler import Job, JobFn, SchedulerManager, create_scheduler_framework
from shared_core.security.cors import CorsConfig, development_cors_config, production_cors_config
from shared_core.validation.middleware import RequestValidationMiddleware
from shared_core.workflow import WorkflowTaskQueue
from starlette.middleware.cors import CORSMiddleware

from app.api import (
    health_router,
    instances_router,
    reports_router,
    statistics_router,
    workflows_router,
)
from app.config.keys import load_public_key
from app.config.settings import Settings, get_settings
from app.middleware.timing import TimingMiddleware
from app.models.enums import WorkflowTriggerType
from app.models.workflow_timer import WorkflowTimer
from app.repositories.workflow_approval import WorkflowApprovalRepository
from app.repositories.workflow_checkpoint import WorkflowCheckpointRepository
from app.repositories.workflow_compensation import WorkflowCompensationRepository
from app.repositories.workflow_definition import WorkflowDefinitionRepository
from app.repositories.workflow_event import WorkflowEventRecordRepository
from app.repositories.workflow_execution_step import WorkflowExecutionStepRepository
from app.repositories.workflow_instance import WorkflowInstanceRepository
from app.repositories.workflow_log import WorkflowLogRepository
from app.repositories.workflow_result import WorkflowResultRepository
from app.repositories.workflow_state import WorkflowStateTransitionRepository
from app.repositories.workflow_timer import WorkflowTimerRepository
from app.repositories.workflow_version import WorkflowVersionRepository
from app.scheduling.registrar import register_timer
from app.services.approval import WorkflowApprovalService
from app.services.checkpoint import WorkflowCheckpointService
from app.services.compensation import WorkflowCompensationService
from app.services.definition import WorkflowDefinitionService
from app.services.event import WorkflowEventService
from app.services.execution import EventPublisher, WorkflowExecutionService
from app.services.instance import WorkflowInstanceService
from app.services.log import WorkflowLogService
from app.services.state import WorkflowStateTransitionService
from app.services.timer import WorkflowTimerService
from app.services.version import WorkflowVersionService
from app.workers.execution_worker import EXECUTION_QUEUE_NAME, build_execution_worker

logger = get_logger("app.startup")


@asynccontextmanager
async def _build_execution_service(
    database: DatabaseFramework,
    http_client: httpx.AsyncClient,
    task_queue: WorkflowTaskQueue,
    publish_event: EventPublisher,
    settings: Settings,
) -> AsyncIterator[WorkflowExecutionService]:
    """Assemble the service :func:`app.workers.execution_worker
    .build_execution_worker` needs, bound to one commit-or-rollback
    session -- the same "session_scope per background job" shape
    ``services/automation-service``'s own ``_build_execution_service``
    established.
    """
    async with session_scope(database.session_factory) as session:
        versions = WorkflowVersionService(WorkflowVersionRepository(session))
        definitions = WorkflowDefinitionService(WorkflowDefinitionRepository(session), versions)
        states = WorkflowStateTransitionService(WorkflowStateTransitionRepository(session))
        logs = WorkflowLogService(WorkflowLogRepository(session))
        events = WorkflowEventService(WorkflowEventRecordRepository(session))
        approvals = WorkflowApprovalService(WorkflowApprovalRepository(session))
        checkpoints = WorkflowCheckpointService(WorkflowCheckpointRepository(session))
        compensations = WorkflowCompensationService(WorkflowCompensationRepository(session))
        yield WorkflowExecutionService(
            WorkflowInstanceRepository(session),
            WorkflowExecutionStepRepository(session),
            WorkflowResultRepository(session),
            definitions,
            versions,
            states,
            logs,
            events,
            approvals,
            checkpoints,
            compensations,
            http_client,
            task_queue,
            automation_service_base_url=settings.service.automation_service_base_url,
            publish_event=publish_event,
            approval_poll_interval_seconds=settings.service.approval_poll_interval_seconds,
            max_loop_iterations=settings.service.max_loop_iterations,
        )


async def _trigger_scheduled_workflow(
    definition_id: UUID,
    database: DatabaseFramework,
    queue_producer: Producer,
) -> None:
    """Create and enqueue a new instance for *definition_id* when a
    ``CRON``/``RECURRING`` timer fires ("Scheduled Resume").

    No caller identity exists for a schedule-fired instance (no
    service-account/machine-credential mechanism has been established
    by any prior AI-IOS prompt) -- ``app/workers/execution_worker.py``
    already honestly skips ``TASK``/``CONNECTOR`` dispatch with no
    caller token, the same documented gap
    ``services/automation-service``'s own scheduled executions accept.
    """
    async with session_scope(database.session_factory) as session:
        definitions = WorkflowDefinitionRepository(session)
        versions = WorkflowVersionRepository(session)
        instances = WorkflowInstanceService(
            WorkflowInstanceRepository(session),
            WorkflowStateTransitionService(WorkflowStateTransitionRepository(session)),
        )
        definition = await definitions.require_by_id(definition_id)
        version = await versions.get_latest_for_definition(definition_id)
        if version is None:
            logger.warning(
                "Scheduled workflow timer fired for a definition with no version yet.",
                extra={"extra_fields": {"definition_id": str(definition_id)}},
            )
            return
        instance = await instances.create(
            organization_id=definition.organization_id,
            project_id=definition.project_id,
            definition_id=definition_id,
            version_id=version.id,
            trigger_type=WorkflowTriggerType.SCHEDULED,
            triggered_by=None,
        )
    await queue_producer.publish(
        EXECUTION_QUEUE_NAME, {"instance_id": str(instance.id), "caller_token": None}
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

    app.state.jwt_public_key = load_public_key(settings.service.jwt_public_key_path)
    app.state.service_settings = settings.service

    app.state.http_client = httpx.AsyncClient(timeout=settings.service.http_client_timeout_seconds)

    queue = await create_queue_framework(settings.rabbitmq)
    app.state.queue_producer = queue.producer
    await queue.manager.declare_queue_with_dlq(EXECUTION_QUEUE_NAME)

    task_queue = WorkflowTaskQueue(queue.manager)
    await task_queue.declare()
    app.state.task_queue = task_queue

    def _execution_service_factory() -> AbstractAsyncContextManager[WorkflowExecutionService]:
        return _build_execution_service(
            database, app.state.http_client, task_queue, app.state.publish_event, settings
        )

    await register_jobs(queue.consumer, [build_execution_worker(_execution_service_factory)])

    scheduler_manager: SchedulerManager = create_scheduler_framework(
        queue.manager, cache.client, queue_name="workflow_scheduler_queue"
    )
    app.state.scheduler_manager = scheduler_manager

    async with session_scope(database.session_factory) as session:
        schedulable_timers = await WorkflowTimerService(
            WorkflowTimerRepository(session)
        ).list_all_schedulable()
    for timer in schedulable_timers:
        register_timer(
            scheduler_manager, timer, _build_scheduled_job_fn(timer, database, queue.producer)
        )
    await scheduler_manager.start()

    logger.info("workflow-runtime-service starting up")
    try:
        yield
    finally:
        await scheduler_manager.stop()
        await database.shutdown()
        await cache.shutdown()
        await events.shutdown()
        await queue.shutdown()
        await app.state.http_client.aclose()
        logger.info("workflow-runtime-service shutting down")


def _build_scheduled_job_fn(
    timer: WorkflowTimer, database: DatabaseFramework, queue_producer: Producer
) -> JobFn:
    """Bind *timer* into the ``shared_core.scheduler.JobFn`` shape
    :func:`~app.scheduling.registrar.register_timer` needs --
    ``Job.fn`` is called with the framework's own ``Job`` object, not
    this service's own :class:`WorkflowTimer`, so the timer this
    specific job represents must be captured in a closure rather than
    read back off the framework job at call time.
    """

    async def _run(_job: Job) -> None:
        await _trigger_scheduled_workflow(timer.definition_id, database, queue_producer)

    return _run


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    settings = get_settings()
    configure_logging(
        service=settings.application.app_name,
        environment=settings.application.environment,
        level=settings.application.log_level,
    )

    app = FastAPI(
        title="AI-IOS Workflow Runtime Service",
        description=(
            "Enterprise workflow runtime -- persistence, distributed dispatch, checkpointing, "
            "replay, rollback, compensation, and human approval around the Workflow SDK's "
            "in-process DAG engine."
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

    # Every router here owns a distinct top-level path segment
    # (/workflows, /workflow-instances, /workflow/statistics,
    # /workflow/reports), so unlike
    # services/configuration-management-service's own profile_router,
    # registration order carries no route-matching hazard here.
    app.include_router(health_router)
    app.include_router(workflows_router)
    app.include_router(instances_router)
    app.include_router(statistics_router)
    app.include_router(reports_router)

    Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=True)

    return app


def _build_cors_config(settings: Settings) -> CorsConfig:
    """Build the CORS policy for the current environment."""
    if settings.application.environment.value == "production":
        return production_cors_config(settings.service.cors_allowed_origins)
    return development_cors_config()


__all__ = ["create_app"]
