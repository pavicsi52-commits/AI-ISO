"""FastAPI dependency injection for the validation service.

One factory function per business service, each building its own
repositories from the request-scoped database session -- routes depend
on services only, never repositories directly. Matches
``services/workflow-runtime-service/app/api/deps.py``'s established
shape, with the addition of :func:`get_collector_registry`
(process-wide, mapping a check's own ``collector_key`` onto the actual
data-gathering function) and :func:`get_execution_service` (composes
nearly every other service in this module -- the validation engine's
own orchestrator).
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
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.registry import CollectorRegistry
from app.notifications.validation_notifications import ValidationNotificationService
from app.repositories.validation_audit import ValidationAuditEntryRepository
from app.repositories.validation_category import ValidationCategoryRepository
from app.repositories.validation_check import ValidationCheckRepository
from app.repositories.validation_exception import ValidationExceptionRepository
from app.repositories.validation_execution import ValidationExecutionRepository
from app.repositories.validation_failure import ValidationFailureRepository
from app.repositories.validation_history import ValidationHistoryRepository
from app.repositories.validation_profile import ValidationProfileRepository
from app.repositories.validation_remediation import ValidationRemediationRepository
from app.repositories.validation_report import ValidationReportRepository
from app.repositories.validation_result import ValidationResultRepository
from app.repositories.validation_result_detail import ValidationResultDetailRepository
from app.repositories.validation_rule import ValidationRuleRepository
from app.repositories.validation_score import ValidationScoreRepository
from app.repositories.validation_statistics import ValidationStatisticsRepository
from app.repositories.validation_target import ValidationTargetRepository
from app.repositories.validation_template import ValidationTemplateRepository
from app.services.audit import ValidationAuditService
from app.services.category import ValidationCategoryService
from app.services.check import ValidationCheckService
from app.services.exception import ValidationExceptionService
from app.services.execution import ValidationExecutionService
from app.services.failure import ValidationFailureService
from app.services.history import ValidationHistoryService
from app.services.profile import ValidationProfileService
from app.services.remediation import ValidationRemediationService
from app.services.report import ValidationReportService
from app.services.result import ValidationResultService
from app.services.rule import ValidationRuleService
from app.services.score import ValidationScoreService
from app.services.statistics import ValidationStatisticsService
from app.services.target import ValidationTargetService
from app.services.template import ValidationTemplateService

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped database session, committing on success."""
    session_factory = request.app.state.db_session_factory
    async with session_scope(session_factory) as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db_session)]


def get_http_client(request: Request) -> httpx.AsyncClient:
    """The process-wide :class:`httpx.AsyncClient` shared by every
    cross-service call this service makes (Inventory, Configuration
    Management, Automation, Workflow Runtime, Discovery).
    """
    return request.app.state.http_client  # type: ignore[no-any-return]


def get_collector_registry(request: Request) -> CollectorRegistry:
    """The process-wide :class:`CollectorRegistry`."""
    return request.app.state.collector_registry  # type: ignore[no-any-return]


def get_queue_producer(request: Request) -> Producer:
    """The process-wide :class:`Producer`, used to enqueue execution
    dispatch onto
    :data:`app.workers.execution_worker.EXECUTION_QUEUE_NAME` instead of
    blocking the triggering HTTP request for a potentially long-running run.
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
    """The raw Bearer token string, forwarded to every collector's own
    outbound client call on this caller's behalf.

    Raises:
        AuthenticationError: If no valid Bearer token is presented.
    """
    if credentials is None:
        raise AuthenticationError("Authentication required.")
    return credentials.credentials


CurrentUserToken = Annotated[str, Depends(get_caller_token)]


def get_notification_service(
    manager: Annotated[NotificationManager, Depends(get_notification_manager)],
) -> ValidationNotificationService:
    """The current request's :class:`ValidationNotificationService`."""
    return ValidationNotificationService(manager)


def get_audit_service(session: DbSession) -> ValidationAuditService:
    """The current request's :class:`ValidationAuditService`."""
    return ValidationAuditService(ValidationAuditEntryRepository(session))


AuditSvc = Annotated[ValidationAuditService, Depends(get_audit_service)]


def get_category_service(session: DbSession) -> ValidationCategoryService:
    """The current request's :class:`ValidationCategoryService`."""
    return ValidationCategoryService(ValidationCategoryRepository(session))


CategorySvc = Annotated[ValidationCategoryService, Depends(get_category_service)]


def get_check_service(session: DbSession) -> ValidationCheckService:
    """The current request's :class:`ValidationCheckService`."""
    return ValidationCheckService(ValidationCheckRepository(session))


CheckSvc = Annotated[ValidationCheckService, Depends(get_check_service)]


def get_rule_service(session: DbSession) -> ValidationRuleService:
    """The current request's :class:`ValidationRuleService`."""
    return ValidationRuleService(ValidationRuleRepository(session))


RuleSvc = Annotated[ValidationRuleService, Depends(get_rule_service)]


def get_target_service(session: DbSession) -> ValidationTargetService:
    """The current request's :class:`ValidationTargetService`."""
    return ValidationTargetService(ValidationTargetRepository(session))


TargetSvc = Annotated[ValidationTargetService, Depends(get_target_service)]


def get_template_service(session: DbSession) -> ValidationTemplateService:
    """The current request's :class:`ValidationTemplateService`."""
    return ValidationTemplateService(ValidationTemplateRepository(session))


TemplateSvc = Annotated[ValidationTemplateService, Depends(get_template_service)]


def get_profile_service(session: DbSession) -> ValidationProfileService:
    """The current request's :class:`ValidationProfileService`."""
    return ValidationProfileService(ValidationProfileRepository(session))


ProfileSvc = Annotated[ValidationProfileService, Depends(get_profile_service)]


def get_result_service(session: DbSession) -> ValidationResultService:
    """The current request's fully-wired :class:`ValidationResultService`."""
    return ValidationResultService(
        ValidationResultRepository(session), ValidationResultDetailRepository(session)
    )


ResultSvc = Annotated[ValidationResultService, Depends(get_result_service)]


def get_failure_service(session: DbSession) -> ValidationFailureService:
    """The current request's :class:`ValidationFailureService`."""
    return ValidationFailureService(ValidationFailureRepository(session))


FailureSvc = Annotated[ValidationFailureService, Depends(get_failure_service)]


def get_score_service(session: DbSession) -> ValidationScoreService:
    """The current request's :class:`ValidationScoreService`."""
    return ValidationScoreService(ValidationScoreRepository(session))


ScoreSvc = Annotated[ValidationScoreService, Depends(get_score_service)]


def get_exception_service(session: DbSession) -> ValidationExceptionService:
    """The current request's :class:`ValidationExceptionService`."""
    return ValidationExceptionService(ValidationExceptionRepository(session))


ExceptionSvc = Annotated[ValidationExceptionService, Depends(get_exception_service)]


def get_remediation_service(session: DbSession) -> ValidationRemediationService:
    """The current request's :class:`ValidationRemediationService`."""
    return ValidationRemediationService(ValidationRemediationRepository(session))


RemediationSvc = Annotated[ValidationRemediationService, Depends(get_remediation_service)]


def get_history_service(session: DbSession) -> ValidationHistoryService:
    """The current request's :class:`ValidationHistoryService`."""
    return ValidationHistoryService(ValidationHistoryRepository(session))


HistorySvc = Annotated[ValidationHistoryService, Depends(get_history_service)]


def get_execution_service(
    request: Request,
    session: DbSession,
    http_client: Annotated[httpx.AsyncClient, Depends(get_http_client)],
    collectors: Annotated[CollectorRegistry, Depends(get_collector_registry)],
) -> ValidationExecutionService:
    """The current request's fully-wired :class:`ValidationExecutionService`."""
    settings = request.app.state.service_settings
    return ValidationExecutionService(
        ValidationExecutionRepository(session),
        ValidationProfileRepository(session),
        ValidationCheckRepository(session),
        ValidationCategoryRepository(session),
        ValidationRuleRepository(session),
        ValidationTargetRepository(session),
        ValidationResultRepository(session),
        ValidationResultDetailRepository(session),
        ValidationFailureRepository(session),
        ValidationScoreRepository(session),
        ValidationHistoryRepository(session),
        http_client,
        collectors,
        inventory_base_url=settings.inventory_service_base_url,
        configuration_base_url=settings.configuration_service_base_url,
        automation_base_url=settings.automation_service_base_url,
        workflow_base_url=settings.workflow_runtime_service_base_url,
        discovery_base_url=settings.discovery_service_base_url,
        publish_event=request.app.state.publish_event,
        max_parallel_checks=settings.max_parallel_checks,
    )


ExecutionSvc = Annotated[ValidationExecutionService, Depends(get_execution_service)]


def get_statistics_service(session: DbSession) -> ValidationStatisticsService:
    """The current request's fully-wired :class:`ValidationStatisticsService`."""
    return ValidationStatisticsService(
        ValidationStatisticsRepository(session),
        ValidationProfileRepository(session),
        ValidationExecutionRepository(session),
        ValidationFailureRepository(session),
        ValidationHistoryRepository(session),
    )


StatisticsSvc = Annotated[ValidationStatisticsService, Depends(get_statistics_service)]


def get_report_service(session: DbSession, statistics: StatisticsSvc) -> ValidationReportService:
    """The current request's fully-wired :class:`ValidationReportService`."""
    return ValidationReportService(
        ValidationReportRepository(session),
        ValidationExecutionRepository(session),
        ValidationResultRepository(session),
        ValidationFailureRepository(session),
        ValidationHistoryRepository(session),
        statistics,
    )


ReportSvc = Annotated[ValidationReportService, Depends(get_report_service)]


__all__ = [
    "AuditSvc",
    "CategorySvc",
    "CheckSvc",
    "CurrentUserId",
    "CurrentUserToken",
    "DbSession",
    "ExceptionSvc",
    "ExecutionSvc",
    "FailureSvc",
    "HistorySvc",
    "ProfileSvc",
    "QueueProducerDep",
    "RemediationSvc",
    "ReportSvc",
    "ResultSvc",
    "RuleSvc",
    "ScoreSvc",
    "StatisticsSvc",
    "TargetSvc",
    "TemplateSvc",
    "get_audit_service",
    "get_caller_token",
    "get_category_service",
    "get_check_service",
    "get_collector_registry",
    "get_current_user_id",
    "get_db_session",
    "get_exception_service",
    "get_execution_service",
    "get_failure_service",
    "get_history_service",
    "get_http_client",
    "get_notification_manager",
    "get_notification_service",
    "get_profile_service",
    "get_queue_producer",
    "get_remediation_service",
    "get_report_service",
    "get_result_service",
    "get_rule_service",
    "get_score_service",
    "get_statistics_service",
    "get_target_service",
    "get_template_service",
]
