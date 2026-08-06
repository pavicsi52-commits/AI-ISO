"""FastAPI dependency injection for the API gateway service.

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

import httpx
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from shared_core.database.session import session_scope
from shared_core.exceptions.authentication import AuthenticationError
from shared_core.security.jwt import decode_token
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.apikey import ApiKeyPermissionRepository, ApiKeyRepository
from app.repositories.client import ApiClientRepository
from app.repositories.governance import (
    ApiAuditRepository,
    ApiReportRepository,
    ApiStatisticRepository,
)
from app.repositories.health import ApiServiceHealthRepository
from app.repositories.quota import ApiQuotaPolicyRepository
from app.repositories.ratelimit import ApiRateLimitPolicyRepository
from app.repositories.request import ApiRequestLogRepository, ApiResponseLogRepository
from app.repositories.route import ApiRouteRepository
from app.repositories.service import ApiServiceRepository
from app.repositories.transformation import ApiTransformationRuleRepository
from app.repositories.version import ApiVersionRepository
from app.services.apikey import ApiKeyService
from app.services.auth import AuthService
from app.services.client import ClientService
from app.services.health import HealthMonitorService
from app.services.proxy import ProxyService
from app.services.quota import QuotaService
from app.services.ratelimit import RateLimitService
from app.services.reporting import AuditService, ReportService, StatisticsService
from app.services.route import RouteService
from app.services.service import ServiceRegistryService
from app.services.transformation import TransformationService
from app.services.version import VersionService
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


def get_http_client(request: Request) -> httpx.AsyncClient:
    """The process-wide, connection-pooled outbound HTTP client the proxy forwards through."""
    return request.app.state.http_client  # type: ignore[no-any-return]


HttpClientDep = Annotated[httpx.AsyncClient, Depends(get_http_client)]


async def get_current_user_id(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
) -> UUID:
    """Resolve the calling (management-API) user's id from their Bearer token.

    Raises:
        AuthenticationError: If no valid Bearer token is presented.
    """
    if credentials is None:
        raise AuthenticationError("Authentication required.")
    public_key = request.app.state.jwt_public_key
    claims = decode_token(credentials.credentials, public_key=public_key)
    return UUID(str(claims["sub"]))


CurrentUserId = Annotated[UUID, Depends(get_current_user_id)]


def get_service_registry(session: DbSession) -> ServiceRegistryService:
    """The current request's service-registry service."""
    return ServiceRegistryService(ApiServiceRepository(session))


ServiceRegistrySvc = Annotated[ServiceRegistryService, Depends(get_service_registry)]


def get_version_service(session: DbSession) -> VersionService:
    """The current request's version service."""
    return VersionService(ApiVersionRepository(session))


VersionSvc = Annotated[VersionService, Depends(get_version_service)]


def get_route_service(session: DbSession) -> RouteService:
    """The current request's route service."""
    return RouteService(ApiRouteRepository(session))


RouteSvc = Annotated[RouteService, Depends(get_route_service)]


def get_client_service(session: DbSession) -> ClientService:
    """The current request's client service."""
    return ClientService(ApiClientRepository(session))


ClientSvc = Annotated[ClientService, Depends(get_client_service)]


def get_api_key_service(session: DbSession) -> ApiKeyService:
    """The current request's API key service."""
    return ApiKeyService(ApiKeyRepository(session))


ApiKeySvc = Annotated[ApiKeyService, Depends(get_api_key_service)]


def get_api_key_permission_repository(session: DbSession) -> ApiKeyPermissionRepository:
    """The current request's API key permission repository."""
    return ApiKeyPermissionRepository(session)


ApiKeyPermissionRepo = Annotated[
    ApiKeyPermissionRepository, Depends(get_api_key_permission_repository)
]


def get_rate_limit_service(session: DbSession, request: Request) -> RateLimitService:
    """The current request's rate-limit service."""
    return RateLimitService(ApiRateLimitPolicyRepository(session), request.app.state.cache_manager)


RateLimitSvc = Annotated[RateLimitService, Depends(get_rate_limit_service)]


def get_quota_service(session: DbSession) -> QuotaService:
    """The current request's quota service."""
    return QuotaService(ApiQuotaPolicyRepository(session))


QuotaSvc = Annotated[QuotaService, Depends(get_quota_service)]


def get_transformation_service(session: DbSession) -> TransformationService:
    """The current request's transformation service."""
    return TransformationService(ApiTransformationRuleRepository(session))


TransformationSvc = Annotated[TransformationService, Depends(get_transformation_service)]


def get_health_monitor(session: DbSession, request: Request) -> HealthMonitorService:
    """This request's own health monitor.

    Built fresh per request against the request-scoped session (an
    ``AsyncSession`` is not safe to hold across concurrent requests as a
    singleton), but sharing ``app.state.circuit_breakers`` -- the one
    process-wide dict every instance's own circuit breaker state lives
    in, so a breaker tripped by one request stays tripped for the next.
    """
    settings = request.app.state.service_settings
    return HealthMonitorService(
        ApiServiceHealthRepository(session),
        failure_threshold=settings.circuit_breaker_failure_threshold,
        recovery_seconds=settings.circuit_breaker_recovery_seconds,
        probe_timeout_seconds=settings.health_probe_timeout_seconds,
        breakers=request.app.state.circuit_breakers,
    )


HealthMonitorSvc = Annotated[HealthMonitorService, Depends(get_health_monitor)]


def get_auth_service(request: Request, api_keys: ApiKeySvc) -> AuthService:
    """The current request's authentication/authorization service."""
    return AuthService(api_keys=api_keys, jwt_public_key=request.app.state.jwt_public_key)


AuthSvc = Annotated[AuthService, Depends(get_auth_service)]


def get_proxy_service(
    session: DbSession,
    http_client: HttpClientDep,
    routes: RouteSvc,
    services: ServiceRegistrySvc,
    rate_limits: RateLimitSvc,
    quotas: QuotaSvc,
    health: HealthMonitorSvc,
    transformations: TransformationSvc,
    publish_event: EventPublisherDep,
    request: Request,
) -> ProxyService:
    """The current request's proxy service."""
    return ProxyService(
        http_client=http_client,
        routes=routes,
        services=services,
        rate_limits=rate_limits,
        quotas=quotas,
        health=health,
        transformations=transformations,
        request_logs=ApiRequestLogRepository(session),
        response_logs=ApiResponseLogRepository(session),
        round_robin_counters=request.app.state.round_robin_counters,
        sticky_maps=request.app.state.sticky_maps,
        publish_event=publish_event,
    )


ProxySvc = Annotated[ProxyService, Depends(get_proxy_service)]


def get_statistics_service(session: DbSession) -> StatisticsService:
    """The current request's statistics service."""
    return StatisticsService(
        ApiStatisticRepository(session),
        ApiRequestLogRepository(session),
        ApiResponseLogRepository(session),
    )


StatisticsSvc = Annotated[StatisticsService, Depends(get_statistics_service)]


def get_report_service(session: DbSession, request: Request) -> ReportService:
    """The current request's report service."""
    settings = request.app.state.service_settings
    return ReportService(
        ApiReportRepository(session),
        ApiRequestLogRepository(session),
        ApiResponseLogRepository(session),
        ApiAuditRepository(session),
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
        ApiAuditRepository(session), session_factory=request.app.state.db_session_factory
    )


AuditSvc = Annotated[AuditService, Depends(get_audit_service)]
