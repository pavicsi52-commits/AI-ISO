"""FastAPI dependency injection for the compliance service.

One factory per business service, each building its own repositories from
the request-scoped session -- routes depend on services only.

**The audit service is given the application's session factory as well as
the request's session.** ``record_failure`` has to commit in a
transaction of its own: a refusal is recorded and then *raised*, and the
raise rolls back the transaction the entry was written in. That bug
shipped in ``services/knowledge-graph-service`` and passed its test for
as long as it was broken, because a request-scoped SAVEPOINT does not
roll back the way a real request does.
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

from app.notifications.compliance_notifications import ComplianceNotificationService
from app.repositories.catalogue import (
    ControlMappingRepository,
    ControlRepository,
    FrameworkRepository,
)
from app.repositories.governance import (
    AuditRepository,
    ExceptionRepository,
    FindingRepository,
    HistoryRepository,
    RemediationRepository,
    ReportRepository,
    RiskRepository,
    ScoreRepository,
    StatisticRepository,
)
from app.repositories.runs import (
    AssessmentRepository,
    EvidenceRepository,
    ResultRepository,
    ScanRepository,
)
from app.services.assessment import AssessmentService
from app.services.catalogue import CatalogueService
from app.services.evidence import EvidenceService
from app.services.finding import FindingService
from app.services.governance import ExceptionService, RemediationService, RiskService
from app.services.reporting import AuditService, ReportService, StatisticsService
from app.services.scoring import ScoringService
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
) -> ComplianceNotificationService:
    """The current request's notification service."""
    return ComplianceNotificationService(manager)


NotificationSvc = Annotated[ComplianceNotificationService, Depends(get_notification_service)]


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


def get_catalogue_service(session: DbSession) -> CatalogueService:
    """The current request's framework and control service."""
    return CatalogueService(
        FrameworkRepository(session),
        ControlRepository(session),
        ControlMappingRepository(session),
    )


CatalogueSvc = Annotated[CatalogueService, Depends(get_catalogue_service)]


def get_evidence_service(
    request: Request, session: DbSession, publish_event: EventPublisherDep
) -> EvidenceService:
    """The current request's evidence service."""
    settings = request.app.state.service_settings
    return EvidenceService(
        EvidenceRepository(session),
        publish_event=publish_event,
        max_payload_bytes=settings.max_evidence_payload_bytes,
        default_validity_days=settings.evidence_default_validity_days,
    )


EvidenceSvc = Annotated[EvidenceService, Depends(get_evidence_service)]


def get_assessment_service(
    request: Request, session: DbSession, publish_event: EventPublisherDep
) -> AssessmentService:
    """The current request's assessment service."""
    settings = request.app.state.service_settings
    return AssessmentService(
        AssessmentRepository(session),
        ResultRepository(session),
        ControlRepository(session),
        FrameworkRepository(session),
        ExceptionRepository(session),
        EvidenceRepository(session),
        publish_event=publish_event,
        max_controls=settings.max_controls_per_assessment,
        max_targets_per_control=settings.max_targets_per_control,
        max_seconds=settings.max_evaluation_seconds,
    )


AssessmentSvc = Annotated[AssessmentService, Depends(get_assessment_service)]


def get_finding_service(
    request: Request,
    session: DbSession,
    notifications: NotificationSvc,
    publish_event: EventPublisherDep,
) -> FindingService:
    """The current request's finding service."""
    settings = request.app.state.service_settings
    return FindingService(
        FindingRepository(session),
        notifications,
        publish_event=publish_event,
        critical_days=settings.finding_due_days_critical,
        high_days=settings.finding_due_days_high,
        medium_days=settings.finding_due_days_medium,
        low_days=settings.finding_due_days_low,
    )


FindingSvc = Annotated[FindingService, Depends(get_finding_service)]


def get_exception_service(
    request: Request,
    session: DbSession,
    notifications: NotificationSvc,
    publish_event: EventPublisherDep,
) -> ExceptionService:
    """The current request's exception service."""
    settings = request.app.state.service_settings
    return ExceptionService(
        ExceptionRepository(session),
        ControlRepository(session),
        notifications,
        publish_event=publish_event,
        max_days=settings.max_exception_days,
        review_interval_days=settings.exception_review_interval_days,
        expiry_warning_days=settings.exception_expiry_warning_days,
    )


ExceptionSvc = Annotated[ExceptionService, Depends(get_exception_service)]


def get_risk_service(
    request: Request,
    session: DbSession,
    notifications: NotificationSvc,
    publish_event: EventPublisherDep,
) -> RiskService:
    """The current request's risk register service."""
    settings = request.app.state.service_settings
    return RiskService(
        RiskRepository(session),
        notifications,
        publish_event=publish_event,
        review_interval_days=settings.risk_review_interval_days,
    )


RiskSvc = Annotated[RiskService, Depends(get_risk_service)]


def get_remediation_service(
    session: DbSession,
    notifications: NotificationSvc,
    publish_event: EventPublisherDep,
) -> RemediationService:
    """The current request's remediation service."""
    return RemediationService(
        RemediationRepository(session),
        FindingRepository(session),
        ResultRepository(session),
        notifications,
        publish_event=publish_event,
    )


RemediationSvc = Annotated[RemediationService, Depends(get_remediation_service)]


def get_scoring_service(
    request: Request, session: DbSession, publish_event: EventPublisherDep
) -> ScoringService:
    """The current request's scoring service."""
    settings = request.app.state.service_settings
    return ScoringService(
        ScoreRepository(session),
        ResultRepository(session),
        AssessmentRepository(session),
        FrameworkRepository(session),
        ControlRepository(session),
        publish_event=publish_event,
        minimum_controls=settings.minimum_controls_for_score,
    )


ScoringSvc = Annotated[ScoringService, Depends(get_scoring_service)]


def get_statistics_service(session: DbSession) -> StatisticsService:
    """The current request's statistics service."""
    return StatisticsService(
        StatisticRepository(session),
        AssessmentRepository(session),
        ScanRepository(session),
        ResultRepository(session),
        EvidenceRepository(session),
        FindingRepository(session),
        RiskRepository(session),
        ExceptionRepository(session),
        RemediationRepository(session),
        ScoreRepository(session),
        ControlRepository(session),
        FrameworkRepository(session),
    )


StatisticsSvc = Annotated[StatisticsService, Depends(get_statistics_service)]


def get_report_service(
    request: Request, session: DbSession, statistics: StatisticsSvc
) -> ReportService:
    """The current request's report service."""
    settings = request.app.state.service_settings
    return ReportService(
        ReportRepository(session),
        statistics,
        FindingRepository(session),
        RiskRepository(session),
        ExceptionRepository(session),
        ControlRepository(session),
        FrameworkRepository(session),
        EvidenceRepository(session),
        AssessmentRepository(session),
        ResultRepository(session),
        ScoreRepository(session),
        AuditRepository(session),
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


def get_scan_repository(session: DbSession) -> ScanRepository:
    """The current request's scan repository."""
    return ScanRepository(session)


ScanRepo = Annotated[ScanRepository, Depends(get_scan_repository)]


def get_history_repository(session: DbSession) -> HistoryRepository:
    """The current request's history repository."""
    return HistoryRepository(session)


HistoryRepo = Annotated[HistoryRepository, Depends(get_history_repository)]
