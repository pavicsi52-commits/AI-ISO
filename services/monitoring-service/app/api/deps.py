"""FastAPI dependency injection for the monitoring service.

One factory function per business service, each building its own
repositories from the request-scoped database session -- routes depend
on services only, never repositories directly. Matches
``services/validation-service/app/api/deps.py``'s established shape.
No :class:`~app.collectors.context.CollectorContext`/
:class:`~app.collectors.registry.CollectorRegistry` wiring here -- every
collection run is scheduler-triggered
(:mod:`app.workers.collection_worker`), never a direct HTTP request, so
the API layer never needs live outbound service clients of its own.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from shared_core.database.session import session_scope
from shared_core.exceptions.authentication import AuthenticationError
from shared_core.security.jwt import decode_token
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.monitoring_audit import MonitoringAuditEntryRepository
from app.repositories.monitoring_availability import MonitoringAvailabilityRepository
from app.repositories.monitoring_collector import MonitoringCollectorRepository
from app.repositories.monitoring_dependency import MonitoringDependencyRepository
from app.repositories.monitoring_health import MonitoringHealthRepository
from app.repositories.monitoring_history import MonitoringHistoryRepository
from app.repositories.monitoring_metric import MonitoringMetricRepository
from app.repositories.monitoring_metric_series import MonitoringMetricSeriesRepository
from app.repositories.monitoring_report import MonitoringReportRepository
from app.repositories.monitoring_retention import MonitoringRetentionRepository
from app.repositories.monitoring_rule import MonitoringRuleRepository
from app.repositories.monitoring_sla import MonitoringSLARepository
from app.repositories.monitoring_slo import MonitoringSLORepository
from app.repositories.monitoring_statistics import MonitoringStatisticsRepository
from app.repositories.monitoring_synthetic_test import MonitoringSyntheticTestRepository
from app.repositories.monitoring_target import MonitoringTargetRepository
from app.repositories.monitoring_threshold import MonitoringThresholdRepository
from app.services.audit import MonitoringAuditService
from app.services.availability import MonitoringAvailabilityService
from app.services.collector import MonitoringCollectorService
from app.services.dependency import MonitoringDependencyService
from app.services.health import MonitoringHealthService
from app.services.history import MonitoringHistoryService
from app.services.metric import MonitoringMetricService
from app.services.metric_series import MonitoringMetricSeriesService
from app.services.performance import MonitoringPerformanceService
from app.services.report import MonitoringReportService
from app.services.retention import MonitoringRetentionService
from app.services.rule import MonitoringRuleService
from app.services.sla import MonitoringSLAService
from app.services.slo import MonitoringSLOService
from app.services.statistics import MonitoringStatisticsService
from app.services.synthetic_test import MonitoringSyntheticTestService
from app.services.target import MonitoringTargetService
from app.services.threshold import MonitoringThresholdService

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped database session, committing on success."""
    session_factory = request.app.state.db_session_factory
    async with session_scope(session_factory) as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db_session)]


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


def get_target_service(session: DbSession) -> MonitoringTargetService:
    """The current request's :class:`MonitoringTargetService`."""
    return MonitoringTargetService(MonitoringTargetRepository(session))


TargetSvc = Annotated[MonitoringTargetService, Depends(get_target_service)]


def get_collector_service(session: DbSession) -> MonitoringCollectorService:
    """The current request's :class:`MonitoringCollectorService`."""
    return MonitoringCollectorService(MonitoringCollectorRepository(session))


CollectorSvc = Annotated[MonitoringCollectorService, Depends(get_collector_service)]


def get_metric_service(session: DbSession) -> MonitoringMetricService:
    """The current request's :class:`MonitoringMetricService`."""
    return MonitoringMetricService(MonitoringMetricRepository(session))


MetricSvc = Annotated[MonitoringMetricService, Depends(get_metric_service)]


def get_metric_series_service(session: DbSession) -> MonitoringMetricSeriesService:
    """The current request's :class:`MonitoringMetricSeriesService`."""
    return MonitoringMetricSeriesService(MonitoringMetricSeriesRepository(session))


MetricSeriesSvc = Annotated[MonitoringMetricSeriesService, Depends(get_metric_series_service)]


def get_health_service(session: DbSession) -> MonitoringHealthService:
    """The current request's :class:`MonitoringHealthService`."""
    return MonitoringHealthService(MonitoringHealthRepository(session))


HealthSvc = Annotated[MonitoringHealthService, Depends(get_health_service)]


def get_availability_service(session: DbSession) -> MonitoringAvailabilityService:
    """The current request's :class:`MonitoringAvailabilityService`."""
    return MonitoringAvailabilityService(MonitoringAvailabilityRepository(session))


AvailabilitySvc = Annotated[MonitoringAvailabilityService, Depends(get_availability_service)]


def get_threshold_service(session: DbSession) -> MonitoringThresholdService:
    """The current request's :class:`MonitoringThresholdService`."""
    return MonitoringThresholdService(MonitoringThresholdRepository(session))


ThresholdSvc = Annotated[MonitoringThresholdService, Depends(get_threshold_service)]


def get_rule_service(session: DbSession) -> MonitoringRuleService:
    """The current request's :class:`MonitoringRuleService`."""
    return MonitoringRuleService(MonitoringRuleRepository(session))


RuleSvc = Annotated[MonitoringRuleService, Depends(get_rule_service)]


def get_sla_service(session: DbSession) -> MonitoringSLAService:
    """The current request's :class:`MonitoringSLAService`."""
    return MonitoringSLAService(MonitoringSLARepository(session))


SLASvc = Annotated[MonitoringSLAService, Depends(get_sla_service)]


def get_slo_service(session: DbSession) -> MonitoringSLOService:
    """The current request's :class:`MonitoringSLOService`."""
    return MonitoringSLOService(MonitoringSLORepository(session))


SLOSvc = Annotated[MonitoringSLOService, Depends(get_slo_service)]


def get_dependency_service(session: DbSession) -> MonitoringDependencyService:
    """The current request's :class:`MonitoringDependencyService`."""
    return MonitoringDependencyService(MonitoringDependencyRepository(session))


DependencySvc = Annotated[MonitoringDependencyService, Depends(get_dependency_service)]


def get_synthetic_test_service(session: DbSession) -> MonitoringSyntheticTestService:
    """The current request's :class:`MonitoringSyntheticTestService`."""
    return MonitoringSyntheticTestService(MonitoringSyntheticTestRepository(session))


SyntheticTestSvc = Annotated[MonitoringSyntheticTestService, Depends(get_synthetic_test_service)]


def get_history_service(session: DbSession) -> MonitoringHistoryService:
    """The current request's :class:`MonitoringHistoryService`."""
    return MonitoringHistoryService(MonitoringHistoryRepository(session))


HistorySvc = Annotated[MonitoringHistoryService, Depends(get_history_service)]


def get_audit_service(session: DbSession) -> MonitoringAuditService:
    """The current request's :class:`MonitoringAuditService`."""
    return MonitoringAuditService(MonitoringAuditEntryRepository(session))


AuditSvc = Annotated[MonitoringAuditService, Depends(get_audit_service)]


def get_retention_service(
    session: DbSession, metric_series: MetricSeriesSvc
) -> MonitoringRetentionService:
    """The current request's fully-wired :class:`MonitoringRetentionService`."""
    return MonitoringRetentionService(MonitoringRetentionRepository(session), metric_series)


RetentionSvc = Annotated[MonitoringRetentionService, Depends(get_retention_service)]


def get_performance_service(session: DbSession) -> MonitoringPerformanceService:
    """The current request's :class:`MonitoringPerformanceService`."""
    return MonitoringPerformanceService(
        MonitoringMetricSeriesRepository(session), MonitoringMetricRepository(session)
    )


PerformanceSvc = Annotated[MonitoringPerformanceService, Depends(get_performance_service)]


def get_statistics_service(
    session: DbSession, health: HealthSvc, availability: AvailabilitySvc
) -> MonitoringStatisticsService:
    """The current request's fully-wired :class:`MonitoringStatisticsService`."""
    return MonitoringStatisticsService(
        MonitoringStatisticsRepository(session),
        MonitoringTargetRepository(session),
        health,
        availability,
        MonitoringSLARepository(session),
        MonitoringSLORepository(session),
    )


StatisticsSvc = Annotated[MonitoringStatisticsService, Depends(get_statistics_service)]


def get_report_service(
    session: DbSession,
    health: HealthSvc,
    availability: AvailabilitySvc,
    performance: PerformanceSvc,
    history: HistorySvc,
    statistics: StatisticsSvc,
) -> MonitoringReportService:
    """The current request's fully-wired :class:`MonitoringReportService`."""
    return MonitoringReportService(
        MonitoringReportRepository(session),
        health,
        availability,
        performance,
        history,
        statistics,
        MonitoringSLARepository(session),
        MonitoringSLORepository(session),
    )


ReportSvc = Annotated[MonitoringReportService, Depends(get_report_service)]


__all__ = [
    "AuditSvc",
    "AvailabilitySvc",
    "CollectorSvc",
    "CurrentUserId",
    "DbSession",
    "DependencySvc",
    "HealthSvc",
    "HistorySvc",
    "MetricSeriesSvc",
    "MetricSvc",
    "PerformanceSvc",
    "ReportSvc",
    "RetentionSvc",
    "RuleSvc",
    "SLASvc",
    "SLOSvc",
    "StatisticsSvc",
    "SyntheticTestSvc",
    "TargetSvc",
    "ThresholdSvc",
    "get_audit_service",
    "get_availability_service",
    "get_collector_service",
    "get_current_user_id",
    "get_db_session",
    "get_dependency_service",
    "get_health_service",
    "get_history_service",
    "get_metric_series_service",
    "get_metric_service",
    "get_performance_service",
    "get_report_service",
    "get_retention_service",
    "get_rule_service",
    "get_sla_service",
    "get_slo_service",
    "get_statistics_service",
    "get_synthetic_test_service",
    "get_target_service",
    "get_threshold_service",
]
