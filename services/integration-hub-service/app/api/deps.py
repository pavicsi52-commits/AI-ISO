"""FastAPI dependency injection for the integration hub service.

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

from app.repositories.connector import (
    ConnectorCategoryRepository,
    ConnectorRepository,
    ConnectorVersionRepository,
)
from app.repositories.credential import ConnectorConnectionRepository, ConnectorCredentialRepository
from app.repositories.event import ConnectorEventRepository
from app.repositories.flow import ConnectorFlowRepository
from app.repositories.governance import (
    ConnectorAuditRepository,
    ConnectorReportRepository,
    ConnectorStatisticRepository,
)
from app.repositories.health import ConnectorHealthRepository
from app.repositories.marketplace import ConnectorMarketplaceRepository
from app.repositories.sync import ConnectorSyncJobRepository
from app.repositories.transformation import ConnectorTransformationRepository
from app.security.credential_resolver import SecretCredentialResolver
from app.services.connection import ConnectionService
from app.services.connector import ConnectorService
from app.services.credential import CredentialService
from app.services.event import EventService
from app.services.flow import FlowService
from app.services.health import HealthService
from app.services.marketplace import MarketplaceService
from app.services.reporting import AuditService, ReportService, StatisticsService
from app.services.sync import SyncService
from app.services.transformation import TransformationService
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
    """The process-wide, connection-pooled outbound HTTP client this service uses."""
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


def get_caller_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
) -> str:
    """The caller's own raw bearer token -- forwarded, never decoded, to
    the Secrets Management Service so its own ACL applies."""
    return credentials.credentials if credentials is not None else ""


CallerToken = Annotated[str, Depends(get_caller_token)]


def get_connector_service(session: DbSession) -> ConnectorService:
    """The current request's connector lifecycle service."""
    return ConnectorService(
        ConnectorRepository(session),
        ConnectorVersionRepository(session),
        ConnectorCategoryRepository(session),
    )


ConnectorSvc = Annotated[ConnectorService, Depends(get_connector_service)]


def get_credential_service(
    session: DbSession, request: Request, http_client: HttpClientDep
) -> CredentialService:
    """The current request's credential service."""
    settings = request.app.state.service_settings
    resolver = SecretCredentialResolver(http_client, base_url=settings.secrets_service_base_url)
    return CredentialService(
        ConnectorCredentialRepository(session),
        encryption_key=settings.secret_encryption_key,
        resolver=resolver,
    )


CredentialSvc = Annotated[CredentialService, Depends(get_credential_service)]


def get_connection_service(session: DbSession, request: Request) -> ConnectionService:
    """The current request's connection-testing service."""
    settings = request.app.state.service_settings
    return ConnectionService(
        ConnectorConnectionRepository(session),
        timeout_seconds=settings.health_check_timeout_seconds,
    )


ConnectionSvc = Annotated[ConnectionService, Depends(get_connection_service)]


def get_health_service(session: DbSession, request: Request) -> HealthService:
    """The current request's health-probing service."""
    settings = request.app.state.service_settings
    return HealthService(
        ConnectorHealthRepository(session),
        timeout_seconds=settings.health_check_timeout_seconds,
        failure_threshold=settings.health_failure_threshold,
    )


HealthSvc = Annotated[HealthService, Depends(get_health_service)]


def get_transformation_service(session: DbSession) -> TransformationService:
    """The current request's transformation service."""
    return TransformationService(ConnectorTransformationRepository(session))


TransformationSvc = Annotated[TransformationService, Depends(get_transformation_service)]


def get_sync_service(
    session: DbSession, transformations: TransformationSvc, publish_event: EventPublisherDep
) -> SyncService:
    """The current request's synchronization service."""
    return SyncService(
        ConnectorSyncJobRepository(session), transformations, publish_event=publish_event
    )


SyncSvc = Annotated[SyncService, Depends(get_sync_service)]


def get_event_service(session: DbSession) -> EventService:
    """The current request's event ingestion/routing service."""
    return EventService(ConnectorEventRepository(session))


EventSvc = Annotated[EventService, Depends(get_event_service)]


def get_flow_service(
    session: DbSession,
    sync: SyncSvc,
    transformations: TransformationSvc,
    events: EventSvc,
    publish_event: EventPublisherDep,
) -> FlowService:
    """The current request's flow-orchestration service."""
    return FlowService(
        ConnectorFlowRepository(session), sync, transformations, events, publish_event=publish_event
    )


FlowSvc = Annotated[FlowService, Depends(get_flow_service)]


def get_marketplace_service(
    session: DbSession, publish_event: EventPublisherDep
) -> MarketplaceService:
    """The current request's marketplace/catalog service."""
    return MarketplaceService(ConnectorMarketplaceRepository(session), publish_event=publish_event)


MarketplaceSvc = Annotated[MarketplaceService, Depends(get_marketplace_service)]


def get_statistics_service(session: DbSession) -> StatisticsService:
    """The current request's statistics service."""
    return StatisticsService(
        ConnectorStatisticRepository(session), ConnectorSyncJobRepository(session)
    )


StatisticsSvc = Annotated[StatisticsService, Depends(get_statistics_service)]


def get_report_service(session: DbSession, request: Request) -> ReportService:
    """The current request's report service."""
    settings = request.app.state.service_settings
    return ReportService(
        ConnectorReportRepository(session),
        ConnectorRepository(session),
        ConnectorSyncJobRepository(session),
        ConnectorHealthRepository(session),
        ConnectorAuditRepository(session),
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
        ConnectorAuditRepository(session), session_factory=request.app.state.db_session_factory
    )


AuditSvc = Annotated[AuditService, Depends(get_audit_service)]
