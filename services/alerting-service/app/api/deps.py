"""FastAPI dependency injection for the alerting service.

One factory function per business service, each building its own
repositories from the request-scoped database session -- routes depend
on services only, never repositories directly. Matches
``services/monitoring-service/app/api/deps.py``'s established shape.
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

from app.notifications.alert_notifications import AlertNotificationService
from app.repositories.alert_acknowledgement import AlertAcknowledgementRepository
from app.repositories.alert_audit import AlertAuditEntryRepository
from app.repositories.alert_condition import AlertConditionRepository
from app.repositories.alert_correlation import AlertCorrelationRepository
from app.repositories.alert_deduplication import AlertDeduplicationRepository
from app.repositories.alert_escalation import AlertEscalationPolicyRepository
from app.repositories.alert_history import AlertHistoryRepository
from app.repositories.alert_instance import AlertInstanceRepository
from app.repositories.alert_maintenance_window import AlertMaintenanceWindowRepository
from app.repositories.alert_notification import AlertNotificationRepository
from app.repositories.alert_oncall_schedule import AlertOnCallScheduleRepository
from app.repositories.alert_report import AlertReportRepository
from app.repositories.alert_route import AlertRouteRepository
from app.repositories.alert_rule import AlertRuleRepository
from app.repositories.alert_statistics import AlertStatisticsRepository
from app.repositories.alert_suppression import AlertSuppressionRepository
from app.services.acknowledgement import AlertAcknowledgementService
from app.services.alert import AlertService
from app.services.audit import AlertAuditService
from app.services.correlation import AlertCorrelationService
from app.services.deduplication import AlertDeduplicationService
from app.services.dispatch import AlertDispatchService
from app.services.escalation import AlertEscalationPolicyService
from app.services.ingestion import AlertIngestionService
from app.services.maintenance_window import AlertMaintenanceWindowService
from app.services.oncall import AlertOnCallScheduleService
from app.services.report import AlertReportService
from app.services.route import AlertRouteService
from app.services.rule import AlertRuleService
from app.services.statistics import AlertStatisticsService
from app.services.suppression import AlertSuppressionService

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped database session, committing on success."""
    session_factory = request.app.state.db_session_factory
    async with session_scope(session_factory) as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db_session)]


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


def get_alert_service(session: DbSession) -> AlertService:
    """The current request's :class:`AlertService`."""
    return AlertService(AlertInstanceRepository(session), AlertHistoryRepository(session))


AlertSvc = Annotated[AlertService, Depends(get_alert_service)]


def get_rule_service(session: DbSession) -> AlertRuleService:
    """The current request's :class:`AlertRuleService`."""
    return AlertRuleService(AlertRuleRepository(session), AlertConditionRepository(session))


RuleSvc = Annotated[AlertRuleService, Depends(get_rule_service)]


def get_maintenance_window_service(session: DbSession) -> AlertMaintenanceWindowService:
    """The current request's :class:`AlertMaintenanceWindowService`."""
    return AlertMaintenanceWindowService(AlertMaintenanceWindowRepository(session))


MaintenanceWindowSvc = Annotated[
    AlertMaintenanceWindowService, Depends(get_maintenance_window_service)
]


def get_oncall_service(session: DbSession) -> AlertOnCallScheduleService:
    """The current request's :class:`AlertOnCallScheduleService`."""
    return AlertOnCallScheduleService(AlertOnCallScheduleRepository(session))


OnCallSvc = Annotated[AlertOnCallScheduleService, Depends(get_oncall_service)]


def get_route_service(session: DbSession) -> AlertRouteService:
    """The current request's :class:`AlertRouteService`."""
    return AlertRouteService(AlertRouteRepository(session))


RouteSvc = Annotated[AlertRouteService, Depends(get_route_service)]


def get_escalation_service(session: DbSession) -> AlertEscalationPolicyService:
    """The current request's :class:`AlertEscalationPolicyService`."""
    return AlertEscalationPolicyService(AlertEscalationPolicyRepository(session))


EscalationSvc = Annotated[AlertEscalationPolicyService, Depends(get_escalation_service)]


def get_suppression_service(session: DbSession) -> AlertSuppressionService:
    """The current request's :class:`AlertSuppressionService`."""
    return AlertSuppressionService(
        AlertSuppressionRepository(session), AlertMaintenanceWindowRepository(session)
    )


SuppressionSvc = Annotated[AlertSuppressionService, Depends(get_suppression_service)]


def get_acknowledgement_service(session: DbSession) -> AlertAcknowledgementService:
    """The current request's :class:`AlertAcknowledgementService`."""
    return AlertAcknowledgementService(AlertAcknowledgementRepository(session))


AcknowledgementSvc = Annotated[AlertAcknowledgementService, Depends(get_acknowledgement_service)]


def get_correlation_service(session: DbSession) -> AlertCorrelationService:
    """The current request's :class:`AlertCorrelationService`."""
    return AlertCorrelationService(
        AlertCorrelationRepository(session), AlertInstanceRepository(session)
    )


CorrelationSvc = Annotated[AlertCorrelationService, Depends(get_correlation_service)]


def get_audit_service(session: DbSession) -> AlertAuditService:
    """The current request's :class:`AlertAuditService`."""
    return AlertAuditService(AlertAuditEntryRepository(session))


AuditSvc = Annotated[AlertAuditService, Depends(get_audit_service)]


def get_statistics_service(session: DbSession) -> AlertStatisticsService:
    """The current request's fully-wired :class:`AlertStatisticsService`."""
    return AlertStatisticsService(
        AlertStatisticsRepository(session),
        AlertInstanceRepository(session),
        AlertAcknowledgementRepository(session),
        AlertHistoryRepository(session),
    )


StatisticsSvc = Annotated[AlertStatisticsService, Depends(get_statistics_service)]


def get_report_service(
    session: DbSession, alerts: AlertSvc, statistics: StatisticsSvc
) -> AlertReportService:
    """The current request's fully-wired :class:`AlertReportService`."""
    return AlertReportService(AlertReportRepository(session), alerts, statistics)


ReportSvc = Annotated[AlertReportService, Depends(get_report_service)]


def get_notification_service(
    session: DbSession,
    request: Request,
    manager: Annotated[NotificationManager, Depends(get_notification_manager)],
) -> AlertNotificationService:
    """The current request's :class:`AlertNotificationService`."""
    return AlertNotificationService(
        AlertNotificationRepository(session),
        manager,
        publish_event=request.app.state.publish_event,
    )


NotificationSvc = Annotated[AlertNotificationService, Depends(get_notification_service)]


def get_ingestion_service(
    request: Request,
    session: DbSession,
    alerts: AlertSvc,
    suppression: SuppressionSvc,
    correlation: CorrelationSvc,
) -> AlertIngestionService:
    """The current request's fully-wired :class:`AlertIngestionService`."""
    settings = request.app.state.service_settings
    return AlertIngestionService(
        alerts,
        AlertInstanceRepository(session),
        AlertDeduplicationService(AlertDeduplicationRepository(session)),
        suppression,
        correlation,
        publish_event=request.app.state.publish_event,
        deduplication_window_seconds=settings.default_deduplication_window_seconds,
        correlation_window_seconds=settings.default_correlation_window_seconds,
    )


IngestionSvc = Annotated[AlertIngestionService, Depends(get_ingestion_service)]


def get_dispatch_service(
    request: Request,
    alerts: AlertSvc,
    session: DbSession,
    routes: RouteSvc,
    policies: EscalationSvc,
    oncall: OnCallSvc,
    notifications: NotificationSvc,
) -> AlertDispatchService:
    """The current request's fully-wired :class:`AlertDispatchService`."""
    return AlertDispatchService(
        alerts,
        AlertInstanceRepository(session),
        routes,
        policies,
        oncall,
        notifications,
        publish_event=request.app.state.publish_event,
    )


DispatchSvc = Annotated[AlertDispatchService, Depends(get_dispatch_service)]


__all__ = [
    "AcknowledgementSvc",
    "AlertSvc",
    "AuditSvc",
    "CorrelationSvc",
    "CurrentUserId",
    "DbSession",
    "DispatchSvc",
    "EscalationSvc",
    "IngestionSvc",
    "MaintenanceWindowSvc",
    "NotificationSvc",
    "OnCallSvc",
    "ReportSvc",
    "RouteSvc",
    "RuleSvc",
    "StatisticsSvc",
    "SuppressionSvc",
    "get_acknowledgement_service",
    "get_alert_service",
    "get_audit_service",
    "get_correlation_service",
    "get_current_user_id",
    "get_db_session",
    "get_dispatch_service",
    "get_escalation_service",
    "get_ingestion_service",
    "get_maintenance_window_service",
    "get_notification_manager",
    "get_notification_service",
    "get_oncall_service",
    "get_report_service",
    "get_route_service",
    "get_rule_service",
    "get_statistics_service",
    "get_suppression_service",
]
