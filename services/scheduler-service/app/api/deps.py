"""FastAPI dependency injection for the scheduler service.

One factory per business service, each building its own repositories
from the request-scoped session -- routes depend on services only.

**The audit service is given the application's session factory as well
as the request's session.** ``record_failure`` has to commit in a
transaction of its own: a refusal is recorded and then *raised*, and the
raise rolls back the transaction the entry was written in.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from shared_core.database.session import session_scope
from shared_core.exceptions.authentication import AuthenticationError
from shared_core.notifications.manager import NotificationManager
from shared_core.security.jwt import decode_token
from sqlalchemy.ext.asyncio import AsyncSession

from app.notifications.scheduler_notifications import SchedulerNotificationService
from app.repositories.dependency import JobDependencyRepository
from app.repositories.execution import JobExecutionLogRepository, JobExecutionRepository
from app.repositories.governance import (
    SchedulerAuditRepository,
    SchedulerReportRepository,
    SchedulerStatisticRepository,
)
from app.repositories.history import JobFailureRepository, JobHistoryRepository
from app.repositories.holiday import HolidayCalendarRepository
from app.repositories.job import ScheduledJobRepository
from app.repositories.maintenance import MaintenanceWindowRepository
from app.repositories.priority import JobPriorityPolicyRepository
from app.repositories.retry import JobRetryPolicyRepository
from app.repositories.trigger import JobScheduleRepository, JobTriggerRepository
from app.services.dependency import DependencyService
from app.services.execution import ExecutionService
from app.services.holiday import HolidayService
from app.services.job import JobService
from app.services.maintenance import MaintenanceWindowService
from app.services.priority import PriorityService
from app.services.recovery import RecoveryService
from app.services.reporting import AuditService, ReportService, StatisticsService
from app.services.trigger import TriggerService
from app.types import EventPublisher

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped database session, committing on success."""
    session_factory = request.app.state.db_session_factory
    async with session_scope(session_factory) as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db_session)]


def get_event_publisher(request: Request) -> EventPublisher:
    """The process-wide domain-event publisher."""
    return request.app.state.publish_event  # type: ignore[no-any-return]


EventPublisherDep = Annotated[EventPublisher, Depends(get_event_publisher)]


def get_notification_manager(request: Request) -> NotificationManager:
    """The process-wide notification manager."""
    return request.app.state.notification_manager  # type: ignore[no-any-return]


def get_notification_service(
    manager: Annotated[NotificationManager, Depends(get_notification_manager)],
) -> SchedulerNotificationService:
    """The current request's notification service."""
    return SchedulerNotificationService(manager)


NotificationSvc = Annotated[SchedulerNotificationService, Depends(get_notification_service)]


async def get_current_user_id(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
) -> UUID:
    """Resolve the calling user's id from their Bearer token.

    Raises:
        AuthenticationError: If no valid Bearer token is presented.
    """
    if credentials is None:
        raise AuthenticationError("Authentication required.")
    public_key = request.app.state.jwt_public_key
    claims = decode_token(credentials.credentials, public_key=public_key)
    return UUID(str(claims["sub"]))


CurrentUserId = Annotated[UUID, Depends(get_current_user_id)]


def get_job_service(session: DbSession, publish_event: EventPublisherDep) -> JobService:
    """The current request's job service."""
    return JobService(
        ScheduledJobRepository(session), JobHistoryRepository(session), publish_event=publish_event
    )


JobSvc = Annotated[JobService, Depends(get_job_service)]


def get_trigger_service(session: DbSession, publish_event: EventPublisherDep) -> TriggerService:
    """The current request's trigger service."""
    return TriggerService(
        JobTriggerRepository(session),
        JobScheduleRepository(session),
        ScheduledJobRepository(session),
        HolidayCalendarRepository(session),
        publish_event=publish_event,
    )


TriggerSvc = Annotated[TriggerService, Depends(get_trigger_service)]


def get_dependency_service(session: DbSession) -> DependencyService:
    """The current request's dependency service."""
    return DependencyService(
        JobDependencyRepository(session),
        ScheduledJobRepository(session),
        JobExecutionRepository(session),
    )


DependencySvc = Annotated[DependencyService, Depends(get_dependency_service)]


def get_execution_service(
    session: DbSession,
    notifications: NotificationSvc,
    publish_event: EventPublisherDep,
    request: Request,
) -> ExecutionService:
    """The current request's execution service."""
    settings = request.app.state.service_settings
    job_service = JobService(
        ScheduledJobRepository(session), JobHistoryRepository(session), publish_event=publish_event
    )
    return ExecutionService(
        JobExecutionRepository(session),
        JobExecutionLogRepository(session),
        JobFailureRepository(session),
        ScheduledJobRepository(session),
        JobRetryPolicyRepository(session),
        job_service,
        notifications,
        publish_event=publish_event,
        default_max_attempts=settings.default_max_attempts,
        default_base_delay_seconds=settings.default_base_delay_seconds,
        default_max_delay_seconds=settings.default_max_delay_seconds,
    )


ExecutionSvc = Annotated[ExecutionService, Depends(get_execution_service)]


def get_priority_service(session: DbSession) -> PriorityService:
    """The current request's priority policy service."""
    return PriorityService(JobPriorityPolicyRepository(session))


PrioritySvc = Annotated[PriorityService, Depends(get_priority_service)]


def get_maintenance_service(
    session: DbSession, publish_event: EventPublisherDep
) -> MaintenanceWindowService:
    """The current request's maintenance window service."""
    return MaintenanceWindowService(
        MaintenanceWindowRepository(session), publish_event=publish_event
    )


MaintenanceSvc = Annotated[MaintenanceWindowService, Depends(get_maintenance_service)]


def get_holiday_service(session: DbSession) -> HolidayService:
    """The current request's holiday calendar service."""
    return HolidayService(HolidayCalendarRepository(session))


HolidaySvc = Annotated[HolidayService, Depends(get_holiday_service)]


def get_recovery_service(
    session: DbSession,
    notifications: NotificationSvc,
    execution_service: ExecutionSvc,
    publish_event: EventPublisherDep,
) -> RecoveryService:
    """The current request's recovery service."""
    return RecoveryService(
        JobFailureRepository(session),
        ScheduledJobRepository(session),
        execution_service,
        notifications,
        publish_event=publish_event,
    )


RecoverySvc = Annotated[RecoveryService, Depends(get_recovery_service)]


def get_statistics_service(session: DbSession) -> StatisticsService:
    """The current request's statistics service."""
    return StatisticsService(
        SchedulerStatisticRepository(session),
        ScheduledJobRepository(session),
        JobExecutionRepository(session),
    )


StatisticsSvc = Annotated[StatisticsService, Depends(get_statistics_service)]


def get_report_service(
    session: DbSession, statistics: StatisticsSvc, request: Request
) -> ReportService:
    """The current request's report service."""
    settings = request.app.state.service_settings
    return ReportService(
        SchedulerReportRepository(session),
        ScheduledJobRepository(session),
        JobExecutionRepository(session),
        JobFailureRepository(session),
        statistics,
        max_rows=settings.max_report_rows,
    )


ReportSvc = Annotated[ReportService, Depends(get_report_service)]


def get_audit_service(request: Request, session: DbSession) -> AuditService:
    """The current request's audit service.

    Given the application's session factory as well as the request's
    session, so ``record_failure`` can commit independently of the
    request that is about to raise.
    """
    return AuditService(
        SchedulerAuditRepository(session), session_factory=request.app.state.db_session_factory
    )


AuditSvc = Annotated[AuditService, Depends(get_audit_service)]


def get_history_repository(session: DbSession) -> JobHistoryRepository:
    """The current request's job history repository."""
    return JobHistoryRepository(session)


HistoryRepo = Annotated[JobHistoryRepository, Depends(get_history_repository)]


def get_retry_policy_repository(session: DbSession) -> JobRetryPolicyRepository:
    """The current request's retry policy repository."""
    return JobRetryPolicyRepository(session)


RetryPolicyRepo = Annotated[JobRetryPolicyRepository, Depends(get_retry_policy_repository)]
