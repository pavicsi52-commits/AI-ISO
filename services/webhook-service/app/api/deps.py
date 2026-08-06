"""FastAPI dependency injection for the webhook service.

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

from app.repositories.delivery import WebhookDeliveryAttemptRepository, WebhookDeliveryRepository
from app.repositories.endpoint import WebhookEndpointRepository
from app.repositories.event import WebhookEventRepository
from app.repositories.filter import WebhookFilterRepository
from app.repositories.governance import (
    WebhookAuditRepository,
    WebhookReportRepository,
    WebhookStatisticRepository,
)
from app.repositories.idempotency import WebhookIdempotencyKeyRepository
from app.repositories.replay import WebhookReplayJobRepository
from app.repositories.retry import WebhookDeadLetterRepository, WebhookRetryQueueRepository
from app.repositories.signature import WebhookSignatureRepository
from app.repositories.subscription import WebhookSubscriptionRepository
from app.repositories.transformation import WebhookTransformationRepository
from app.services.delivery import DeliveryService
from app.services.endpoint import EndpointService
from app.services.event import EventService
from app.services.filter import FilterService
from app.services.idempotency import IdempotencyService
from app.services.replay import ReplayService
from app.services.reporting import AuditService, ReportService, StatisticsService
from app.services.signature import SignatureService
from app.services.subscription import SubscriptionService
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
    """The process-wide, connection-pooled outbound HTTP client deliveries forward through."""
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


def get_endpoint_service(session: DbSession) -> EndpointService:
    """The current request's endpoint service."""
    return EndpointService(WebhookEndpointRepository(session))


EndpointSvc = Annotated[EndpointService, Depends(get_endpoint_service)]


def get_subscription_service(session: DbSession) -> SubscriptionService:
    """The current request's subscription service."""
    return SubscriptionService(WebhookSubscriptionRepository(session))


SubscriptionSvc = Annotated[SubscriptionService, Depends(get_subscription_service)]


def get_filter_service(session: DbSession) -> FilterService:
    """The current request's filter service."""
    return FilterService(WebhookFilterRepository(session))


FilterSvc = Annotated[FilterService, Depends(get_filter_service)]


def get_transformation_service(session: DbSession) -> TransformationService:
    """The current request's transformation service."""
    return TransformationService(WebhookTransformationRepository(session))


TransformationSvc = Annotated[TransformationService, Depends(get_transformation_service)]


def get_signature_service(session: DbSession, request: Request) -> SignatureService:
    """The current request's signature service."""
    settings = request.app.state.service_settings
    return SignatureService(
        WebhookSignatureRepository(session), encryption_key=settings.secret_encryption_key
    )


SignatureSvc = Annotated[SignatureService, Depends(get_signature_service)]


def get_idempotency_service(session: DbSession, request: Request) -> IdempotencyService:
    """The current request's idempotency service."""
    settings = request.app.state.service_settings
    return IdempotencyService(
        WebhookIdempotencyKeyRepository(session), ttl_seconds=settings.idempotency_key_ttl_seconds
    )


IdempotencySvc = Annotated[IdempotencyService, Depends(get_idempotency_service)]


def get_event_service(session: DbSession, publish_event: EventPublisherDep) -> EventService:
    """The current request's event-ingestion service."""
    return EventService(WebhookEventRepository(session), publish_event=publish_event)


EventSvc = Annotated[EventService, Depends(get_event_service)]


def get_delivery_service(
    session: DbSession,
    http_client: HttpClientDep,
    subscriptions: SubscriptionSvc,
    filters: FilterSvc,
    transformations: TransformationSvc,
    signatures: SignatureSvc,
    publish_event: EventPublisherDep,
) -> DeliveryService:
    """The current request's delivery orchestrator."""
    return DeliveryService(
        http_client=http_client,
        deliveries=WebhookDeliveryRepository(session),
        attempts=WebhookDeliveryAttemptRepository(session),
        endpoints=WebhookEndpointRepository(session),
        retry_queue=WebhookRetryQueueRepository(session),
        dead_letters=WebhookDeadLetterRepository(session),
        subscriptions=subscriptions,
        filters=filters,
        transformations=transformations,
        signatures=signatures,
        publish_event=publish_event,
    )


DeliverySvc = Annotated[DeliveryService, Depends(get_delivery_service)]


def get_replay_service(session: DbSession, delivery: DeliverySvc) -> ReplayService:
    """The current request's replay service."""
    return ReplayService(
        WebhookReplayJobRepository(session), WebhookEventRepository(session), delivery
    )


ReplaySvc = Annotated[ReplayService, Depends(get_replay_service)]


def get_statistics_service(session: DbSession) -> StatisticsService:
    """The current request's statistics service."""
    return StatisticsService(
        WebhookStatisticRepository(session), WebhookDeliveryAttemptRepository(session)
    )


StatisticsSvc = Annotated[StatisticsService, Depends(get_statistics_service)]


def get_report_service(session: DbSession, request: Request) -> ReportService:
    """The current request's report service."""
    settings = request.app.state.service_settings
    return ReportService(
        WebhookReportRepository(session),
        WebhookDeliveryAttemptRepository(session),
        WebhookEventRepository(session),
        WebhookDeadLetterRepository(session),
        WebhookAuditRepository(session),
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
        WebhookAuditRepository(session), session_factory=request.app.state.db_session_factory
    )


AuditSvc = Annotated[AuditService, Depends(get_audit_service)]
