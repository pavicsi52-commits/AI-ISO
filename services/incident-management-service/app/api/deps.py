"""FastAPI dependency injection for the incident management service.

One factory per business service, each building its own repositories
from the request-scoped session -- routes depend on services only.

**The audit service is given the application's session factory as well
as the request's session.** ``record_failure`` has to commit in a
transaction of its own: a refusal is recorded and then *raised*, and the
raise rolls back the transaction the entry was written in. That bug
shipped in ``services/knowledge-graph-service`` and passed its test for
as long as it was broken, because a request-scoped SAVEPOINT does not
roll back the way a real request does -- see Prompt 049 and 051's own
notes on this.
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

from app.notifications.incident_notifications import IncidentNotificationService
from app.repositories.catalogue import IncidentPriorityRepository
from app.repositories.governance import AuditRepository, ReportRepository, StatisticRepository
from app.repositories.impact import AssetImpactRepository, ImpactRepository, ServiceImpactRepository
from app.repositories.incident import IncidentRepository
from app.repositories.major import (
    MajorIncidentRepository,
    WarRoomParticipantRepository,
    WarRoomRepository,
)
from app.repositories.postmortem import ActionItemRepository, PostmortemRepository
from app.repositories.rca import KnownErrorRepository, ProblemRepository, RootCauseRepository
from app.repositories.sla import EscalationRepository, SlaRepository
from app.repositories.timeline import AssignmentRepository, TimelineRepository, WorklogRepository
from app.services.assignment import AssignmentService
from app.services.escalation import EscalationService
from app.services.impact import ImpactService
from app.services.incident import IncidentService
from app.services.major_incident import MajorIncidentService
from app.services.postmortem import PostmortemService
from app.services.rca import ProblemService, RootCauseService
from app.services.reporting import AuditService, ReportService, StatisticsService
from app.services.sla import SlaService
from app.sla.engine import BusinessCalendar
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
) -> IncidentNotificationService:
    """The current request's notification service."""
    return IncidentNotificationService(manager)


NotificationSvc = Annotated[IncidentNotificationService, Depends(get_notification_service)]


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


def get_incident_service(
    session: DbSession,
    notifications: NotificationSvc,
    publish_event: EventPublisherDep,
    request: Request,
) -> IncidentService:
    """The current request's incident service."""
    settings = request.app.state.service_settings
    return IncidentService(
        IncidentRepository(session),
        TimelineRepository(session),
        WorklogRepository(session),
        AssignmentRepository(session),
        notifications,
        publish_event=publish_event,
        correlation_window_minutes=settings.correlation_window_minutes,
    )


IncidentSvc = Annotated[IncidentService, Depends(get_incident_service)]


def get_sla_service(
    session: DbSession,
    notifications: NotificationSvc,
    publish_event: EventPublisherDep,
    request: Request,
) -> SlaService:
    """The current request's SLA service."""
    settings = request.app.state.service_settings
    calendar = BusinessCalendar(
        start_hour=settings.default_business_hours_start,
        end_hour=settings.default_business_hours_end,
        business_days=frozenset(settings.default_business_days),
    )
    return SlaService(
        SlaRepository(session),
        IncidentPriorityRepository(session),
        IncidentRepository(session),
        notifications,
        publish_event=publish_event,
        calendar=calendar,
        warning_percent=settings.sla_warning_threshold_percent,
    )


SlaSvc = Annotated[SlaService, Depends(get_sla_service)]


def get_escalation_service(
    session: DbSession,
    notifications: NotificationSvc,
    publish_event: EventPublisherDep,
    request: Request,
) -> EscalationService:
    """The current request's escalation service."""
    settings = request.app.state.service_settings
    return EscalationService(
        EscalationRepository(session),
        SlaRepository(session),
        IncidentRepository(session),
        notifications,
        publish_event=publish_event,
        max_levels=settings.max_escalation_levels,
    )


EscalationSvc = Annotated[EscalationService, Depends(get_escalation_service)]


def get_assignment_service(session: DbSession, incident_service: IncidentSvc) -> AssignmentService:
    """The current request's assignment service."""
    return AssignmentService(IncidentRepository(session), incident_service)


AssignmentSvc = Annotated[AssignmentService, Depends(get_assignment_service)]


def get_impact_service(session: DbSession) -> ImpactService:
    """The current request's impact service."""
    return ImpactService(
        ImpactRepository(session),
        ServiceImpactRepository(session),
        AssetImpactRepository(session),
        IncidentRepository(session),
    )


ImpactSvc = Annotated[ImpactService, Depends(get_impact_service)]


def get_major_incident_service(
    session: DbSession, notifications: NotificationSvc, publish_event: EventPublisherDep
) -> MajorIncidentService:
    """The current request's major incident and war room service."""
    return MajorIncidentService(
        MajorIncidentRepository(session),
        WarRoomRepository(session),
        WarRoomParticipantRepository(session),
        IncidentRepository(session),
        notifications,
        publish_event=publish_event,
    )


MajorIncidentSvc = Annotated[MajorIncidentService, Depends(get_major_incident_service)]


def get_root_cause_service(session: DbSession) -> RootCauseService:
    """The current request's root cause service."""
    return RootCauseService(RootCauseRepository(session), IncidentRepository(session))


RootCauseSvc = Annotated[RootCauseService, Depends(get_root_cause_service)]


def get_problem_service(session: DbSession, publish_event: EventPublisherDep) -> ProblemService:
    """The current request's problem and known-error service."""
    return ProblemService(
        ProblemRepository(session),
        KnownErrorRepository(session),
        IncidentRepository(session),
        publish_event=publish_event,
    )


ProblemSvc = Annotated[ProblemService, Depends(get_problem_service)]


def get_postmortem_service(
    session: DbSession, publish_event: EventPublisherDep
) -> PostmortemService:
    """The current request's postmortem service."""
    return PostmortemService(
        PostmortemRepository(session),
        ActionItemRepository(session),
        IncidentRepository(session),
        publish_event=publish_event,
    )


PostmortemSvc = Annotated[PostmortemService, Depends(get_postmortem_service)]


def get_statistics_service(session: DbSession) -> StatisticsService:
    """The current request's statistics service."""
    return StatisticsService(
        StatisticRepository(session),
        IncidentRepository(session),
        SlaRepository(session),
        EscalationRepository(session),
        MajorIncidentRepository(session),
        ProblemRepository(session),
    )


StatisticsSvc = Annotated[StatisticsService, Depends(get_statistics_service)]


def get_report_service(
    session: DbSession, statistics: StatisticsSvc, request: Request
) -> ReportService:
    """The current request's report service."""
    settings = request.app.state.service_settings
    return ReportService(
        ReportRepository(session),
        IncidentRepository(session),
        statistics,
        MajorIncidentRepository(session),
        ProblemRepository(session),
        PostmortemRepository(session),
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
        AuditRepository(session),
        session_factory=request.app.state.db_session_factory,
    )


AuditSvc = Annotated[AuditService, Depends(get_audit_service)]
