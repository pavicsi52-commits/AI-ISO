"""FastAPI dependency injection for the workflow runtime service.

One factory function per business service, each building its own
repositories from the request-scoped database session -- routes depend
on services only, never repositories directly. Matches
``services/automation-service/app/api/deps.py``'s established shape,
with the addition of :func:`get_task_queue` (process-wide, wrapping
``shared_core.workflow.WorkflowTaskQueue`` for ``QUEUE`` nodes) and
:func:`get_execution_service` (composes nearly every other service in
this module -- the workflow runtime's own orchestrator).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

import httpx
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from shared_core.database.session import session_scope
from shared_core.exceptions.authentication import AuthenticationError
from shared_core.notifications.manager import NotificationManager
from shared_core.queue.producer import Producer
from shared_core.security.jwt import decode_token
from shared_core.workflow import WorkflowTaskQueue
from sqlalchemy.ext.asyncio import AsyncSession

from app.notifications.workflow_notifications import WorkflowNotificationService
from app.repositories.workflow_approval import WorkflowApprovalRepository
from app.repositories.workflow_audit import WorkflowAuditEntryRepository
from app.repositories.workflow_checkpoint import WorkflowCheckpointRepository
from app.repositories.workflow_compensation import WorkflowCompensationRepository
from app.repositories.workflow_context import WorkflowContextEntryRepository
from app.repositories.workflow_definition import WorkflowDefinitionRepository
from app.repositories.workflow_event import WorkflowEventRecordRepository
from app.repositories.workflow_execution_step import WorkflowExecutionStepRepository
from app.repositories.workflow_instance import WorkflowInstanceRepository
from app.repositories.workflow_log import WorkflowLogRepository
from app.repositories.workflow_replay import WorkflowReplayRepository
from app.repositories.workflow_report import WorkflowReportRepository
from app.repositories.workflow_result import WorkflowResultRepository
from app.repositories.workflow_state import WorkflowStateTransitionRepository
from app.repositories.workflow_statistics import WorkflowStatisticsRepository
from app.repositories.workflow_timer import WorkflowTimerRepository
from app.repositories.workflow_variable import WorkflowVariableRepository
from app.repositories.workflow_version import WorkflowVersionRepository
from app.services.approval import WorkflowApprovalService
from app.services.audit import WorkflowAuditService
from app.services.checkpoint import WorkflowCheckpointService
from app.services.compensation import WorkflowCompensationService
from app.services.context import WorkflowContextEntryService
from app.services.definition import WorkflowDefinitionService
from app.services.event import WorkflowEventService
from app.services.execution import WorkflowExecutionService
from app.services.execution_step import WorkflowExecutionStepService
from app.services.instance import WorkflowInstanceService
from app.services.log import WorkflowLogService
from app.services.replay import WorkflowReplayService
from app.services.report import WorkflowReportService
from app.services.rollback import WorkflowRollbackService
from app.services.state import WorkflowStateTransitionService
from app.services.statistics import WorkflowStatisticsService
from app.services.timer import WorkflowTimerService
from app.services.variable import WorkflowVariableService
from app.services.version import WorkflowVersionService

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped database session, committing on success."""
    session_factory = request.app.state.db_session_factory
    async with session_scope(session_factory) as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db_session)]


def get_http_client(request: Request) -> httpx.AsyncClient:
    """The process-wide :class:`httpx.AsyncClient` shared by every
    cross-service call this service makes (Automation, Playbook, Inventory).
    """
    return request.app.state.http_client  # type: ignore[no-any-return]


def get_task_queue(request: Request) -> WorkflowTaskQueue:
    """The process-wide :class:`~shared_core.workflow.WorkflowTaskQueue`, for ``QUEUE`` nodes."""
    return request.app.state.task_queue  # type: ignore[no-any-return]


def get_queue_producer(request: Request) -> Producer:
    """The process-wide :class:`Producer`, used to enqueue instance
    dispatch onto :data:`app.workers.execution_worker.EXECUTION_QUEUE_NAME`
    instead of blocking the triggering HTTP request for a workflow's own runtime.
    """
    return request.app.state.queue_producer  # type: ignore[no-any-return]


QueueProducerDep = Annotated[Producer, Depends(get_queue_producer)]


def get_notification_manager(request: Request) -> NotificationManager:
    """The process-wide :class:`NotificationManager`."""
    return request.app.state.notification_manager  # type: ignore[no-any-return]


async def get_current_user_id(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
) -> UUID:
    """Resolve the calling user's id from a Bearer token issued by
    ``services/authentication-service``.

    Raises:
        AuthenticationError: If no valid Bearer token is presented.
    """
    if credentials is None:
        raise AuthenticationError("Authentication required.")
    public_key = request.app.state.jwt_public_key
    claims = decode_token(credentials.credentials, public_key=public_key)
    return UUID(str(claims["sub"]))


CurrentUserId = Annotated[UUID, Depends(get_current_user_id)]


async def get_caller_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
) -> str:
    """The raw Bearer token string, forwarded to the Automation Service
    for ``TASK``/``CONNECTOR`` node dispatch on this caller's behalf.

    Raises:
        AuthenticationError: If no valid Bearer token is presented.
    """
    if credentials is None:
        raise AuthenticationError("Authentication required.")
    return credentials.credentials


CurrentUserToken = Annotated[str, Depends(get_caller_token)]


def get_notification_service(
    manager: Annotated[NotificationManager, Depends(get_notification_manager)],
) -> WorkflowNotificationService:
    """The current request's :class:`WorkflowNotificationService`."""
    return WorkflowNotificationService(manager)


def get_audit_service(session: DbSession) -> WorkflowAuditService:
    """The current request's :class:`WorkflowAuditService`."""
    return WorkflowAuditService(WorkflowAuditEntryRepository(session))


AuditSvc = Annotated[WorkflowAuditService, Depends(get_audit_service)]


def get_log_service(session: DbSession) -> WorkflowLogService:
    """The current request's :class:`WorkflowLogService`."""
    return WorkflowLogService(WorkflowLogRepository(session))


LogSvc = Annotated[WorkflowLogService, Depends(get_log_service)]


def get_execution_step_service(session: DbSession) -> WorkflowExecutionStepService:
    """The current request's :class:`WorkflowExecutionStepService`."""
    return WorkflowExecutionStepService(WorkflowExecutionStepRepository(session))


ExecutionStepSvc = Annotated[WorkflowExecutionStepService, Depends(get_execution_step_service)]


def get_event_service(session: DbSession) -> WorkflowEventService:
    """The current request's :class:`WorkflowEventService`."""
    return WorkflowEventService(WorkflowEventRecordRepository(session))


EventSvc = Annotated[WorkflowEventService, Depends(get_event_service)]


def get_state_service(session: DbSession) -> WorkflowStateTransitionService:
    """The current request's :class:`WorkflowStateTransitionService`."""
    return WorkflowStateTransitionService(WorkflowStateTransitionRepository(session))


StateSvc = Annotated[WorkflowStateTransitionService, Depends(get_state_service)]


def get_context_service(session: DbSession) -> WorkflowContextEntryService:
    """The current request's :class:`WorkflowContextEntryService`."""
    return WorkflowContextEntryService(WorkflowContextEntryRepository(session))


ContextSvc = Annotated[WorkflowContextEntryService, Depends(get_context_service)]


def get_variable_service(session: DbSession) -> WorkflowVariableService:
    """The current request's :class:`WorkflowVariableService`."""
    return WorkflowVariableService(WorkflowVariableRepository(session))


VariableSvc = Annotated[WorkflowVariableService, Depends(get_variable_service)]


def get_timer_service(session: DbSession) -> WorkflowTimerService:
    """The current request's :class:`WorkflowTimerService`."""
    return WorkflowTimerService(WorkflowTimerRepository(session))


TimerSvc = Annotated[WorkflowTimerService, Depends(get_timer_service)]


def get_compensation_service(session: DbSession) -> WorkflowCompensationService:
    """The current request's :class:`WorkflowCompensationService`."""
    return WorkflowCompensationService(WorkflowCompensationRepository(session))


CompensationSvc = Annotated[WorkflowCompensationService, Depends(get_compensation_service)]


def get_checkpoint_service(session: DbSession) -> WorkflowCheckpointService:
    """The current request's :class:`WorkflowCheckpointService`."""
    return WorkflowCheckpointService(WorkflowCheckpointRepository(session))


CheckpointSvc = Annotated[WorkflowCheckpointService, Depends(get_checkpoint_service)]


def get_approval_service(session: DbSession) -> WorkflowApprovalService:
    """The current request's :class:`WorkflowApprovalService`."""
    return WorkflowApprovalService(WorkflowApprovalRepository(session))


ApprovalSvc = Annotated[WorkflowApprovalService, Depends(get_approval_service)]


def get_version_service(session: DbSession) -> WorkflowVersionService:
    """The current request's :class:`WorkflowVersionService`."""
    return WorkflowVersionService(WorkflowVersionRepository(session))


VersionSvc = Annotated[WorkflowVersionService, Depends(get_version_service)]


def get_definition_service(session: DbSession, versions: VersionSvc) -> WorkflowDefinitionService:
    """The current request's fully-wired :class:`WorkflowDefinitionService`."""
    return WorkflowDefinitionService(WorkflowDefinitionRepository(session), versions)


DefinitionSvc = Annotated[WorkflowDefinitionService, Depends(get_definition_service)]


def get_instance_service(session: DbSession, states: StateSvc) -> WorkflowInstanceService:
    """The current request's fully-wired :class:`WorkflowInstanceService`."""
    return WorkflowInstanceService(WorkflowInstanceRepository(session), states)


InstanceSvc = Annotated[WorkflowInstanceService, Depends(get_instance_service)]


def get_execution_service(
    request: Request,
    session: DbSession,
    definitions: DefinitionSvc,
    versions: VersionSvc,
    states: StateSvc,
    logs: LogSvc,
    events: EventSvc,
    approvals: ApprovalSvc,
    checkpoints: CheckpointSvc,
    compensations: CompensationSvc,
    http_client: Annotated[httpx.AsyncClient, Depends(get_http_client)],
    task_queue: Annotated[WorkflowTaskQueue, Depends(get_task_queue)],
) -> WorkflowExecutionService:
    """The current request's fully-wired :class:`WorkflowExecutionService`."""
    settings = request.app.state.service_settings
    return WorkflowExecutionService(
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
        automation_service_base_url=settings.automation_service_base_url,
        publish_event=request.app.state.publish_event,
        approval_poll_interval_seconds=settings.approval_poll_interval_seconds,
        max_loop_iterations=settings.max_loop_iterations,
    )


ExecutionSvc = Annotated[WorkflowExecutionService, Depends(get_execution_service)]


def get_rollback_service(
    session: DbSession,
    definitions: DefinitionSvc,
    versions: VersionSvc,
    compensations: CompensationSvc,
) -> WorkflowRollbackService:
    """The current request's fully-wired :class:`WorkflowRollbackService`."""
    return WorkflowRollbackService(
        WorkflowInstanceRepository(session),
        WorkflowExecutionStepRepository(session),
        definitions,
        versions,
        compensations,
    )


RollbackSvc = Annotated[WorkflowRollbackService, Depends(get_rollback_service)]


def get_replay_service(
    request: Request, session: DbSession, execution: ExecutionSvc
) -> WorkflowReplayService:
    """The current request's fully-wired :class:`WorkflowReplayService`."""
    return WorkflowReplayService(
        WorkflowReplayRepository(session),
        WorkflowInstanceRepository(session),
        WorkflowCheckpointRepository(session),
        execution,
        publish_event=request.app.state.publish_event,
    )


ReplaySvc = Annotated[WorkflowReplayService, Depends(get_replay_service)]


def get_statistics_service(session: DbSession) -> WorkflowStatisticsService:
    """The current request's fully-wired :class:`WorkflowStatisticsService`."""
    return WorkflowStatisticsService(
        WorkflowStatisticsRepository(session),
        WorkflowDefinitionRepository(session),
        WorkflowInstanceRepository(session),
        WorkflowExecutionStepRepository(session),
        WorkflowApprovalRepository(session),
        WorkflowCheckpointRepository(session),
        WorkflowReplayRepository(session),
    )


StatisticsSvc = Annotated[WorkflowStatisticsService, Depends(get_statistics_service)]


def get_report_service(session: DbSession, statistics: StatisticsSvc) -> WorkflowReportService:
    """The current request's fully-wired :class:`WorkflowReportService`."""
    return WorkflowReportService(
        WorkflowReportRepository(session),
        WorkflowInstanceRepository(session),
        WorkflowExecutionStepRepository(session),
        WorkflowApprovalRepository(session),
        statistics,
    )


ReportSvc = Annotated[WorkflowReportService, Depends(get_report_service)]


__all__ = [
    "ApprovalSvc",
    "AuditSvc",
    "CheckpointSvc",
    "CompensationSvc",
    "ContextSvc",
    "CurrentUserId",
    "CurrentUserToken",
    "DbSession",
    "DefinitionSvc",
    "EventSvc",
    "ExecutionStepSvc",
    "ExecutionSvc",
    "InstanceSvc",
    "LogSvc",
    "QueueProducerDep",
    "ReplaySvc",
    "ReportSvc",
    "RollbackSvc",
    "StateSvc",
    "StatisticsSvc",
    "TimerSvc",
    "VariableSvc",
    "VersionSvc",
    "get_approval_service",
    "get_audit_service",
    "get_caller_token",
    "get_checkpoint_service",
    "get_compensation_service",
    "get_context_service",
    "get_current_user_id",
    "get_db_session",
    "get_definition_service",
    "get_event_service",
    "get_execution_service",
    "get_execution_step_service",
    "get_http_client",
    "get_instance_service",
    "get_log_service",
    "get_notification_manager",
    "get_notification_service",
    "get_queue_producer",
    "get_replay_service",
    "get_report_service",
    "get_rollback_service",
    "get_state_service",
    "get_statistics_service",
    "get_task_queue",
    "get_timer_service",
    "get_variable_service",
    "get_version_service",
]
