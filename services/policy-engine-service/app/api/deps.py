"""FastAPI dependency injection for the policy engine service.

One factory per business service, each building its own repositories from
the request-scoped session -- routes depend on services only.

**The audit service is given the application's session factory as well as
the request's session.** ``record_denied`` has to commit in a transaction
of its own: a refusal is recorded and then *raised*, and the raise rolls
back the transaction the entry was written in. That bug shipped in
``services/knowledge-graph-service`` and passed its test for as long as
it was broken, because a request-scoped SAVEPOINT does not roll back the
way a real request does.
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

from app.models.enums import PolicyEffect
from app.notifications.policy_notifications import PolicyNotificationService
from app.repositories.policy import (
    PolicyAttributeRepository,
    PolicyCategoryRepository,
    PolicyConditionRepository,
    PolicyRepository,
    PolicyRuleRepository,
    PolicyVersionRepository,
)
from app.repositories.runtime import (
    PolicyApprovalRepository,
    PolicyAuditRepository,
    PolicyDecisionRepository,
    PolicyExceptionRepository,
    PolicyQuotaRepository,
    PolicyReportRepository,
    PolicySimulationRepository,
    PolicyStatisticsRepository,
    PolicyViolationRepository,
)
from app.services.approval import ApprovalService
from app.services.compliance import AuditService, ComplianceService
from app.services.decision import DecisionService
from app.services.policy import PolicyService
from app.services.quota import QuotaService
from app.services.simulation import SimulationService
from app.services.statistics import ReportService, StatisticsService
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
) -> PolicyNotificationService:
    """The current request's notification service."""
    return PolicyNotificationService(manager)


NotificationSvc = Annotated[PolicyNotificationService, Depends(get_notification_service)]


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


def get_policy_service(session: DbSession, publish_event: EventPublisherDep) -> PolicyService:
    """The current request's policy authoring service."""
    return PolicyService(
        PolicyRepository(session),
        PolicyRuleRepository(session),
        PolicyConditionRepository(session),
        PolicyVersionRepository(session),
        publish_event=publish_event,
    )


PolicySvc = Annotated[PolicyService, Depends(get_policy_service)]


def get_decision_service(request: Request, session: DbSession) -> DecisionService:
    """The current request's decision service."""
    settings = request.app.state.service_settings
    return DecisionService(
        PolicyRepository(session),
        PolicyDecisionRepository(session),
        PolicyExceptionRepository(session),
        PolicyQuotaRepository(session),
        PolicyAttributeRepository(session),
        default_effect=PolicyEffect(settings.default_effect_on_no_match),
        fail_closed=settings.fail_closed,
        max_policies=settings.max_policies_per_evaluation,
        quota_enforcement=settings.quota_enforcement_enabled,
        quota_warning_threshold=settings.quota_warning_threshold,
        slow_threshold_ms=settings.max_evaluation_milliseconds,
    )


DecisionSvc = Annotated[DecisionService, Depends(get_decision_service)]


def get_approval_service(
    request: Request,
    session: DbSession,
    notifications: NotificationSvc,
    publish_event: EventPublisherDep,
) -> ApprovalService:
    """The current request's approval service."""
    settings = request.app.state.service_settings
    return ApprovalService(
        PolicyApprovalRepository(session),
        notifications,
        publish_event=publish_event,
        expiry_hours=settings.approval_expiry_hours,
        emergency_enabled=settings.emergency_approval_enabled,
    )


ApprovalSvc = Annotated[ApprovalService, Depends(get_approval_service)]


def get_quota_service(
    request: Request,
    session: DbSession,
    notifications: NotificationSvc,
    publish_event: EventPublisherDep,
) -> QuotaService:
    """The current request's quota service."""
    settings = request.app.state.service_settings
    return QuotaService(
        PolicyQuotaRepository(session),
        notifications,
        publish_event=publish_event,
        warning_threshold=settings.quota_warning_threshold,
    )


QuotaSvc = Annotated[QuotaService, Depends(get_quota_service)]


def get_simulation_service(
    request: Request,
    session: DbSession,
    notifications: NotificationSvc,
    publish_event: EventPublisherDep,
) -> SimulationService:
    """The current request's simulation service."""
    settings = request.app.state.service_settings
    return SimulationService(
        PolicyRepository(session),
        PolicySimulationRepository(session),
        notifications,
        PolicyRuleRepository(session),
        PolicyConditionRepository(session),
        publish_event=publish_event,
        max_requests=settings.max_simulation_requests,
        default_effect=PolicyEffect(settings.default_effect_on_no_match),
        fail_closed=settings.fail_closed,
        max_policies=settings.max_policies_per_evaluation,
    )


SimulationSvc = Annotated[SimulationService, Depends(get_simulation_service)]


def get_compliance_service(
    session: DbSession,
    notifications: NotificationSvc,
    publish_event: EventPublisherDep,
) -> ComplianceService:
    """The current request's compliance service."""
    return ComplianceService(
        PolicyViolationRepository(session),
        PolicyExceptionRepository(session),
        notifications,
        publish_event=publish_event,
    )


ComplianceSvc = Annotated[ComplianceService, Depends(get_compliance_service)]


def get_statistics_service(session: DbSession) -> StatisticsService:
    """The current request's statistics service."""
    return StatisticsService(
        PolicyRepository(session),
        PolicyDecisionRepository(session),
        PolicyViolationRepository(session),
        PolicyApprovalRepository(session),
        PolicyStatisticsRepository(session),
    )


StatisticsSvc = Annotated[StatisticsService, Depends(get_statistics_service)]


def get_report_service(session: DbSession, statistics: StatisticsSvc) -> ReportService:
    """The current request's report service."""
    return ReportService(
        PolicyReportRepository(session),
        PolicyRepository(session),
        PolicyDecisionRepository(session),
        PolicyViolationRepository(session),
        PolicyApprovalRepository(session),
        statistics,
    )


ReportSvc = Annotated[ReportService, Depends(get_report_service)]


def get_audit_service(request: Request, session: DbSession) -> AuditService:
    """The current request's audit service.

    Given the application's session factory as well as the request's
    session, so ``record_denied`` can commit independently of the request
    that is about to raise.
    """
    return AuditService(
        PolicyAuditRepository(session),
        session_factory=request.app.state.db_session_factory,
    )


AuditSvc = Annotated[AuditService, Depends(get_audit_service)]


def get_category_repository(session: DbSession) -> PolicyCategoryRepository:
    """The current request's category repository."""
    return PolicyCategoryRepository(session)


CategoryRepo = Annotated[PolicyCategoryRepository, Depends(get_category_repository)]


def get_attribute_repository(session: DbSession) -> PolicyAttributeRepository:
    """The current request's attribute catalogue repository."""
    return PolicyAttributeRepository(session)


AttributeRepo = Annotated[PolicyAttributeRepository, Depends(get_attribute_repository)]


__all__ = [
    "ApprovalSvc",
    "AttributeRepo",
    "AuditSvc",
    "CategoryRepo",
    "ComplianceSvc",
    "CurrentUserId",
    "DbSession",
    "DecisionSvc",
    "EventPublisherDep",
    "NotificationSvc",
    "PolicySvc",
    "QuotaSvc",
    "ReportSvc",
    "SimulationSvc",
    "StatisticsSvc",
    "get_approval_service",
    "get_attribute_repository",
    "get_audit_service",
    "get_category_repository",
    "get_compliance_service",
    "get_current_user_id",
    "get_db_session",
    "get_decision_service",
    "get_event_publisher",
    "get_notification_manager",
    "get_notification_service",
    "get_policy_service",
    "get_quota_service",
    "get_report_service",
    "get_simulation_service",
    "get_statistics_service",
]
