"""FastAPI dependency injection for the automation service.

One factory function per business service, each building its own
repositories from the request-scoped database session -- routes depend
on services only, never repositories directly. Matches
``services/configuration-management-service/app/api/deps.py``'s
established shape, with the addition of :func:`get_connector_manager`
(process-wide, per docs/040's own CONNECTOR INTEGRATION section --
pooled connections are reused across requests) and
:func:`get_inventory_client`/:func:`get_configuration_client` for this
service's own cross-service reads.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

import httpx
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from shared_core.connectors.manager import ConnectorManager
from shared_core.database.session import session_scope
from shared_core.exceptions.authentication import AuthenticationError
from shared_core.notifications.manager import NotificationManager
from shared_core.queue.producer import Producer
from shared_core.security.jwt import decode_token
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.configuration_client import ConfigurationClient
from app.inventory.inventory_client import InventoryClient
from app.notifications.automation_notifications import AutomationNotificationService
from app.repositories.automation_approval import AutomationApprovalRepository
from app.repositories.automation_artifact import AutomationArtifactRepository
from app.repositories.automation_audit import AutomationAuditRepository
from app.repositories.automation_execution import AutomationExecutionRepository
from app.repositories.automation_execution_log import AutomationExecutionLogRepository
from app.repositories.automation_execution_plan import AutomationExecutionPlanRepository
from app.repositories.automation_execution_step import AutomationExecutionStepRepository
from app.repositories.automation_job import AutomationJobRepository
from app.repositories.automation_output import AutomationOutputRepository
from app.repositories.automation_parameter import AutomationParameterRepository
from app.repositories.automation_report import AutomationReportRepository
from app.repositories.automation_result import AutomationResultRepository
from app.repositories.automation_retry_history import AutomationRetryHistoryRepository
from app.repositories.automation_rollback import AutomationRollbackRepository
from app.repositories.automation_schedule import AutomationScheduleRepository
from app.repositories.automation_statistics import AutomationStatisticsRepository
from app.repositories.automation_target import AutomationTargetRepository
from app.repositories.automation_template import AutomationTemplateRepository
from app.repositories.automation_variable import AutomationVariableRepository
from app.secrets.credential_resolver import SecretCredentialResolver
from app.services.approval import AutomationApprovalService
from app.services.artifact import AutomationArtifactService
from app.services.audit import AutomationAuditService
from app.services.execution import AutomationExecutionService
from app.services.execution_log import AutomationExecutionLogService
from app.services.execution_plan import AutomationExecutionPlanService
from app.services.job import AutomationJobService
from app.services.parameter import AutomationParameterService
from app.services.report import AutomationReportService
from app.services.rollback import AutomationRollbackService
from app.services.schedule import AutomationScheduleService
from app.services.statistics import AutomationStatisticsService
from app.services.target import AutomationTargetService
from app.services.template import AutomationTemplateService
from app.services.variable import AutomationVariableService

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped database session, committing on success."""
    session_factory = request.app.state.db_session_factory
    async with session_scope(session_factory) as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db_session)]


def get_http_client(request: Request) -> httpx.AsyncClient:
    """The process-wide :class:`httpx.AsyncClient` shared by every
    cross-service call this service makes (Secrets Management,
    Inventory, Configuration Management).
    """
    return request.app.state.http_client  # type: ignore[no-any-return]


def get_connector_manager(request: Request) -> ConnectorManager:
    """The process-wide :class:`ConnectorManager`, holding this
    service's own connector registry and pooled connections.
    """
    return request.app.state.connector_manager  # type: ignore[no-any-return]


def get_queue_producer(request: Request) -> Producer:
    """The process-wide :class:`Producer`, used to enqueue execution
    dispatch onto :data:`app.workers.execution_worker.EXECUTION_QUEUE_NAME`
    ("Async Execution"/"Queue Framework Integration") instead of blocking
    the triggering HTTP request for a job's own runtime.
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
    """The raw Bearer token string, forwarded to the Secrets Management,
    Inventory, and Configuration Management services on this caller's behalf.

    Raises:
        AuthenticationError: If no valid Bearer token is presented.
    """
    if credentials is None:
        raise AuthenticationError("Authentication required.")
    return credentials.credentials


CurrentUserToken = Annotated[str, Depends(get_caller_token)]


def get_notification_service(
    manager: Annotated[NotificationManager, Depends(get_notification_manager)],
) -> AutomationNotificationService:
    """The current request's :class:`AutomationNotificationService`."""
    return AutomationNotificationService(manager)


def get_credential_resolver(
    client: Annotated[httpx.AsyncClient, Depends(get_http_client)], request: Request
) -> SecretCredentialResolver:
    """The current request's :class:`SecretCredentialResolver`."""
    settings = request.app.state.service_settings
    return SecretCredentialResolver(client, base_url=settings.secrets_service_base_url)


def get_inventory_client(
    client: Annotated[httpx.AsyncClient, Depends(get_http_client)], request: Request
) -> InventoryClient:
    """The current request's :class:`InventoryClient`."""
    settings = request.app.state.service_settings
    return InventoryClient(client, base_url=settings.inventory_service_base_url)


def get_configuration_client(
    client: Annotated[httpx.AsyncClient, Depends(get_http_client)], request: Request
) -> ConfigurationClient:
    """The current request's :class:`ConfigurationClient`."""
    settings = request.app.state.service_settings
    return ConfigurationClient(client, base_url=settings.configuration_service_base_url)


def get_audit_service(session: DbSession) -> AutomationAuditService:
    """The current request's :class:`AutomationAuditService`."""
    return AutomationAuditService(AutomationAuditRepository(session))


AuditSvc = Annotated[AutomationAuditService, Depends(get_audit_service)]


def get_job_service(request: Request, session: DbSession, audit: AuditSvc) -> AutomationJobService:
    """The current request's fully-wired :class:`AutomationJobService`."""
    return AutomationJobService(
        AutomationJobRepository(session),
        audit,
        publish_event=getattr(request.app.state, "publish_event", None),
    )


JobSvc = Annotated[AutomationJobService, Depends(get_job_service)]


def get_target_service(session: DbSession) -> AutomationTargetService:
    """The current request's :class:`AutomationTargetService`."""
    return AutomationTargetService(AutomationTargetRepository(session))


TargetSvc = Annotated[AutomationTargetService, Depends(get_target_service)]


def get_variable_service(session: DbSession) -> AutomationVariableService:
    """The current request's :class:`AutomationVariableService`."""
    return AutomationVariableService(AutomationVariableRepository(session))


VariableSvc = Annotated[AutomationVariableService, Depends(get_variable_service)]


def get_parameter_service(session: DbSession) -> AutomationParameterService:
    """The current request's fully-wired :class:`AutomationParameterService`."""
    return AutomationParameterService(
        AutomationParameterRepository(session), AutomationJobRepository(session)
    )


ParameterSvc = Annotated[AutomationParameterService, Depends(get_parameter_service)]


def get_template_service(session: DbSession) -> AutomationTemplateService:
    """The current request's :class:`AutomationTemplateService`."""
    return AutomationTemplateService(AutomationTemplateRepository(session))


TemplateSvc = Annotated[AutomationTemplateService, Depends(get_template_service)]


def get_execution_service(
    request: Request,
    session: DbSession,
    connector_manager: Annotated[ConnectorManager, Depends(get_connector_manager)],
    credentials: Annotated[SecretCredentialResolver, Depends(get_credential_resolver)],
) -> AutomationExecutionService:
    """The current request's fully-wired :class:`AutomationExecutionService`."""
    settings = request.app.state.service_settings
    return AutomationExecutionService(
        AutomationExecutionRepository(session),
        AutomationExecutionStepRepository(session),
        AutomationExecutionLogRepository(session),
        AutomationOutputRepository(session),
        AutomationResultRepository(session),
        AutomationRetryHistoryRepository(session),
        AutomationJobRepository(session),
        AutomationTargetRepository(session),
        connector_manager,
        credentials,
        max_parallel_targets=settings.max_parallel_targets,
        publish_event=getattr(request.app.state, "publish_event", None),
    )


ExecutionSvc = Annotated[AutomationExecutionService, Depends(get_execution_service)]


def get_execution_log_service(session: DbSession) -> AutomationExecutionLogService:
    """The current request's :class:`AutomationExecutionLogService`."""
    return AutomationExecutionLogService(AutomationExecutionLogRepository(session))


ExecutionLogSvc = Annotated[AutomationExecutionLogService, Depends(get_execution_log_service)]


def get_artifact_service(session: DbSession) -> AutomationArtifactService:
    """The current request's :class:`AutomationArtifactService`."""
    return AutomationArtifactService(AutomationArtifactRepository(session))


ArtifactSvc = Annotated[AutomationArtifactService, Depends(get_artifact_service)]


def get_rollback_service(request: Request, session: DbSession) -> AutomationRollbackService:
    """The current request's fully-wired :class:`AutomationRollbackService`."""
    return AutomationRollbackService(
        AutomationRollbackRepository(session),
        AutomationExecutionRepository(session),
        publish_event=getattr(request.app.state, "publish_event", None),
    )


RollbackSvc = Annotated[AutomationRollbackService, Depends(get_rollback_service)]


def get_approval_service(request: Request, session: DbSession) -> AutomationApprovalService:
    """The current request's fully-wired :class:`AutomationApprovalService`."""
    return AutomationApprovalService(
        AutomationApprovalRepository(session),
        AutomationExecutionRepository(session),
        publish_event=getattr(request.app.state, "publish_event", None),
    )


ApprovalSvc = Annotated[AutomationApprovalService, Depends(get_approval_service)]


def get_schedule_service(session: DbSession) -> AutomationScheduleService:
    """The current request's :class:`AutomationScheduleService`."""
    return AutomationScheduleService(AutomationScheduleRepository(session))


ScheduleSvc = Annotated[AutomationScheduleService, Depends(get_schedule_service)]


def get_execution_plan_service(session: DbSession) -> AutomationExecutionPlanService:
    """The current request's :class:`AutomationExecutionPlanService`."""
    return AutomationExecutionPlanService(AutomationExecutionPlanRepository(session))


ExecutionPlanSvc = Annotated[AutomationExecutionPlanService, Depends(get_execution_plan_service)]


def get_statistics_service(session: DbSession) -> AutomationStatisticsService:
    """The current request's :class:`AutomationStatisticsService`."""
    return AutomationStatisticsService(
        AutomationStatisticsRepository(session),
        AutomationJobRepository(session),
        AutomationExecutionRepository(session),
        AutomationExecutionStepRepository(session),
        AutomationTargetRepository(session),
    )


StatisticsSvc = Annotated[AutomationStatisticsService, Depends(get_statistics_service)]


def get_report_service(
    session: DbSession, jobs: JobSvc, executions: ExecutionSvc, statistics: StatisticsSvc
) -> AutomationReportService:
    """The current request's fully-wired :class:`AutomationReportService`."""
    return AutomationReportService(
        AutomationReportRepository(session), jobs, executions, statistics
    )


ReportSvc = Annotated[AutomationReportService, Depends(get_report_service)]


__all__ = [
    "ApprovalSvc",
    "ArtifactSvc",
    "AuditSvc",
    "CurrentUserId",
    "CurrentUserToken",
    "DbSession",
    "ExecutionLogSvc",
    "ExecutionPlanSvc",
    "ExecutionSvc",
    "JobSvc",
    "ParameterSvc",
    "QueueProducerDep",
    "ReportSvc",
    "RollbackSvc",
    "ScheduleSvc",
    "StatisticsSvc",
    "TargetSvc",
    "TemplateSvc",
    "VariableSvc",
    "get_approval_service",
    "get_artifact_service",
    "get_audit_service",
    "get_caller_token",
    "get_configuration_client",
    "get_connector_manager",
    "get_credential_resolver",
    "get_current_user_id",
    "get_db_session",
    "get_execution_log_service",
    "get_execution_plan_service",
    "get_execution_service",
    "get_http_client",
    "get_inventory_client",
    "get_job_service",
    "get_notification_manager",
    "get_notification_service",
    "get_parameter_service",
    "get_queue_producer",
    "get_report_service",
    "get_rollback_service",
    "get_schedule_service",
    "get_statistics_service",
    "get_target_service",
    "get_template_service",
    "get_variable_service",
]
