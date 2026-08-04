"""FastAPI dependency injection for the change management service.

One factory per business service, each building its own repositories
from the request-scoped session -- routes depend on services only.

**The audit service is given the application's session factory as well
as the request's session.** ``record_failure`` has to commit in a
transaction of its own: a refusal is recorded and then *raised*, and the
raise rolls back the transaction the entry was written in. See
Prompt 049/051/052's own notes on this.
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

from app.notifications.change_notifications import ChangeNotificationService
from app.repositories.approval import ChangeApprovalRepository
from app.repositories.cab import ChangeCabRepository, ChangeCabVoteRepository
from app.repositories.calendar import ChangeCalendarRepository
from app.repositories.catalogue import (
    ChangeCategoryRepository,
    ChangePriorityRepository,
    ChangeStatusRepository,
    ChangeTypeRepository,
)
from app.repositories.change import ChangeRelationshipRepository, ChangeRequestRepository
from app.repositories.conflict import ChangeConflictRepository
from app.repositories.governance import (
    ChangeAuditRepository,
    ChangeReportRepository,
    ChangeStatisticRepository,
)
from app.repositories.implementation import (
    ChangeImplementationRepository,
    ChangeRollbackRepository,
    ChangeTaskRepository,
    ChangeValidationRepository,
)
from app.repositories.pir import ChangePostReviewActionItemRepository, ChangePostReviewRepository
from app.repositories.risk import ChangeRiskAssessmentRepository
from app.services.approval import ApprovalService
from app.services.cab import CabService
from app.services.calendar import CalendarService
from app.services.change import ChangeService
from app.services.conflict import ConflictService
from app.services.implementation import ImplementationService
from app.services.pir import PirService
from app.services.reporting import AuditService, ReportService, StatisticsService
from app.services.risk import RiskService
from app.services.rollback import RollbackService
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
) -> ChangeNotificationService:
    """The current request's notification service."""
    return ChangeNotificationService(manager)


NotificationSvc = Annotated[ChangeNotificationService, Depends(get_notification_service)]


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


def get_change_service(session: DbSession, publish_event: EventPublisherDep) -> ChangeService:
    """The current request's change service."""
    return ChangeService(
        ChangeRequestRepository(session),
        ChangeRelationshipRepository(session),
        ChangeCalendarRepository(session),
        publish_event=publish_event,
    )


ChangeSvc = Annotated[ChangeService, Depends(get_change_service)]


def get_risk_service(session: DbSession, publish_event: EventPublisherDep) -> RiskService:
    """The current request's risk service.

    ``standard_change_requires_cab`` is a platform default, not yet an
    organization-configurable setting -- ``ChangeTypeRecord.requires_cab``
    exists precisely to become that override, but wiring it through
    means one more repository call on every risk assessment, deferred
    until a real caller needs it.
    """
    return RiskService(
        ChangeRiskAssessmentRepository(session),
        ChangeRequestRepository(session),
        publish_event=publish_event,
        standard_change_requires_cab=False,
    )


RiskSvc = Annotated[RiskService, Depends(get_risk_service)]


def get_approval_service(
    session: DbSession,
    notifications: NotificationSvc,
    publish_event: EventPublisherDep,
    request: Request,
) -> ApprovalService:
    """The current request's approval service."""
    settings = request.app.state.service_settings
    return ApprovalService(
        ChangeApprovalRepository(session),
        ChangeRequestRepository(session),
        notifications,
        publish_event=publish_event,
        minimum_approvals_high_risk=settings.minimum_approvals_high_risk,
    )


ApprovalSvc = Annotated[ApprovalService, Depends(get_approval_service)]


def get_cab_service(
    session: DbSession,
    notifications: NotificationSvc,
    publish_event: EventPublisherDep,
    request: Request,
) -> CabService:
    """The current request's CAB service."""
    settings = request.app.state.service_settings
    return CabService(
        ChangeCabRepository(session),
        ChangeCabVoteRepository(session),
        ChangeRequestRepository(session),
        notifications,
        publish_event=publish_event,
        quorum_fraction=settings.cab_quorum_fraction,
    )


CabSvc = Annotated[CabService, Depends(get_cab_service)]


def get_calendar_service(session: DbSession) -> CalendarService:
    """The current request's calendar service."""
    return CalendarService(ChangeCalendarRepository(session))


CalendarSvc = Annotated[CalendarService, Depends(get_calendar_service)]


def get_conflict_service(session: DbSession, request: Request) -> ConflictService:
    """The current request's conflict service."""
    settings = request.app.state.service_settings
    return ConflictService(
        ChangeConflictRepository(session),
        ChangeRequestRepository(session),
        slack_hours=settings.conflict_detection_window_hours,
    )


ConflictSvc = Annotated[ConflictService, Depends(get_conflict_service)]


def get_implementation_service(
    session: DbSession, notifications: NotificationSvc, publish_event: EventPublisherDep
) -> ImplementationService:
    """The current request's implementation service."""
    return ImplementationService(
        ChangeTaskRepository(session),
        ChangeImplementationRepository(session),
        ChangeValidationRepository(session),
        ChangeRequestRepository(session),
        notifications,
        publish_event=publish_event,
    )


ImplementationSvc = Annotated[ImplementationService, Depends(get_implementation_service)]


def get_rollback_service(
    session: DbSession, notifications: NotificationSvc, publish_event: EventPublisherDep
) -> RollbackService:
    """The current request's rollback service."""
    return RollbackService(
        ChangeRollbackRepository(session),
        ChangeRequestRepository(session),
        notifications,
        publish_event=publish_event,
    )


RollbackSvc = Annotated[RollbackService, Depends(get_rollback_service)]


def get_pir_service(session: DbSession, publish_event: EventPublisherDep) -> PirService:
    """The current request's PIR service."""
    return PirService(
        ChangePostReviewRepository(session),
        ChangePostReviewActionItemRepository(session),
        ChangeRequestRepository(session),
        publish_event=publish_event,
    )


PirSvc = Annotated[PirService, Depends(get_pir_service)]


def get_statistics_service(session: DbSession) -> StatisticsService:
    """The current request's statistics service."""
    return StatisticsService(
        ChangeStatisticRepository(session),
        ChangeRequestRepository(session),
        ChangeConflictRepository(session),
    )


StatisticsSvc = Annotated[StatisticsService, Depends(get_statistics_service)]


def get_report_service(
    session: DbSession, statistics: StatisticsSvc, request: Request
) -> ReportService:
    """The current request's report service."""
    settings = request.app.state.service_settings
    return ReportService(
        ChangeReportRepository(session),
        ChangeRequestRepository(session),
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
        ChangeAuditRepository(session),
        session_factory=request.app.state.db_session_factory,
    )


AuditSvc = Annotated[AuditService, Depends(get_audit_service)]


def get_category_repository(session: DbSession) -> ChangeCategoryRepository:
    """The current request's category catalogue repository."""
    return ChangeCategoryRepository(session)


CategoryRepo = Annotated[ChangeCategoryRepository, Depends(get_category_repository)]


def get_type_repository(session: DbSession) -> ChangeTypeRepository:
    """The current request's process-type catalogue repository."""
    return ChangeTypeRepository(session)


TypeRepo = Annotated[ChangeTypeRepository, Depends(get_type_repository)]


def get_priority_repository(session: DbSession) -> ChangePriorityRepository:
    """The current request's priority catalogue repository."""
    return ChangePriorityRepository(session)


PriorityRepo = Annotated[ChangePriorityRepository, Depends(get_priority_repository)]


def get_status_repository(session: DbSession) -> ChangeStatusRepository:
    """The current request's status catalogue repository."""
    return ChangeStatusRepository(session)


StatusRepo = Annotated[ChangeStatusRepository, Depends(get_status_repository)]
