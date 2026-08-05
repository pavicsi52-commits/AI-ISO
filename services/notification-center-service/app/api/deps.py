"""FastAPI dependency injection for the notification center service.

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

from app.repositories.announcement import (
    NotificationAnnouncementRepository,
    NotificationBroadcastRepository,
)
from app.repositories.channel import NotificationChannelConfigRepository
from app.repositories.delivery import (
    NotificationDeliveryAttemptRepository,
    NotificationDeliveryRepository,
)
from app.repositories.governance import (
    NotificationAuditRepository,
    NotificationReportRepository,
    NotificationStatisticRepository,
)
from app.repositories.notification import NotificationRepository
from app.repositories.preference import NotificationPreferenceRepository
from app.repositories.retry import (
    NotificationDeadLetterRepository,
    NotificationRetryQueueRepository,
)
from app.repositories.subscription import NotificationSubscriptionRepository
from app.repositories.template import (
    NotificationTemplateRepository,
    NotificationTemplateVersionRepository,
)
from app.services.announcement import AnnouncementService
from app.services.broadcast import BroadcastService
from app.services.channel import ChannelConfigService
from app.services.delivery import DeliveryService, build_delivery_service
from app.services.digest import DigestService
from app.services.notification import NotificationService
from app.services.preference import PreferenceService
from app.services.reporting import AuditService, ReportService, StatisticsService
from app.services.subscription import SubscriptionService
from app.services.template import TemplateService
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
    """The process-wide `shared_core` notification manager."""
    return request.app.state.notification_manager  # type: ignore[no-any-return]


NotificationManagerDep = Annotated[NotificationManager, Depends(get_notification_manager)]


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


def get_notification_service(
    session: DbSession, publish_event: EventPublisherDep
) -> NotificationService:
    """The current request's notification service."""
    return NotificationService(NotificationRepository(session), publish_event=publish_event)


NotificationSvc = Annotated[NotificationService, Depends(get_notification_service)]


def get_preference_service(session: DbSession) -> PreferenceService:
    """The current request's preference service."""
    return PreferenceService(NotificationPreferenceRepository(session))


PreferenceSvc = Annotated[PreferenceService, Depends(get_preference_service)]


def get_channel_service(session: DbSession) -> ChannelConfigService:
    """The current request's channel configuration service."""
    return ChannelConfigService(NotificationChannelConfigRepository(session))


ChannelSvc = Annotated[ChannelConfigService, Depends(get_channel_service)]


def get_subscription_service(session: DbSession) -> SubscriptionService:
    """The current request's subscription service."""
    return SubscriptionService(NotificationSubscriptionRepository(session))


SubscriptionSvc = Annotated[SubscriptionService, Depends(get_subscription_service)]


def get_template_service(session: DbSession) -> TemplateService:
    """The current request's template service."""
    return TemplateService(
        NotificationTemplateRepository(session), NotificationTemplateVersionRepository(session)
    )


TemplateSvc = Annotated[TemplateService, Depends(get_template_service)]


def get_delivery_service(
    session: DbSession,
    manager: NotificationManagerDep,
    publish_event: EventPublisherDep,
    request: Request,
) -> DeliveryService:
    """The current request's delivery service."""
    settings = request.app.state.service_settings
    return build_delivery_service(session, manager, settings, publish_event=publish_event)


DeliverySvc = Annotated[DeliveryService, Depends(get_delivery_service)]


def get_broadcast_service(
    session: DbSession,
    notifications: NotificationSvc,
    delivery: DeliverySvc,
    subscriptions: SubscriptionSvc,
) -> BroadcastService:
    """The current request's broadcast service."""
    return BroadcastService(
        NotificationBroadcastRepository(session), notifications, delivery, subscriptions
    )


BroadcastSvc = Annotated[BroadcastService, Depends(get_broadcast_service)]


def get_announcement_service(
    session: DbSession, publish_event: EventPublisherDep
) -> AnnouncementService:
    """The current request's announcement service."""
    return AnnouncementService(
        NotificationAnnouncementRepository(session), publish_event=publish_event
    )


AnnouncementSvc = Annotated[AnnouncementService, Depends(get_announcement_service)]


def get_digest_service(
    session: DbSession,
    preferences: PreferenceSvc,
    notifications: NotificationSvc,
    delivery: DeliverySvc,
    request: Request,
) -> DigestService:
    """The current request's digest service."""
    settings = request.app.state.service_settings
    return DigestService(
        NotificationRepository(session),
        preferences,
        notifications,
        delivery,
        max_items=settings.digest_max_items,
    )


DigestSvc = Annotated[DigestService, Depends(get_digest_service)]


def get_statistics_service(session: DbSession) -> StatisticsService:
    """The current request's statistics service."""
    return StatisticsService(
        NotificationStatisticRepository(session),
        NotificationRepository(session),
        NotificationDeliveryRepository(session),
    )


StatisticsSvc = Annotated[StatisticsService, Depends(get_statistics_service)]


def get_report_service(session: DbSession, request: Request) -> ReportService:
    """The current request's report service."""
    settings = request.app.state.service_settings
    return ReportService(
        NotificationReportRepository(session),
        NotificationDeliveryRepository(session),
        NotificationDeadLetterRepository(session),
        NotificationRetryQueueRepository(session),
        NotificationAuditRepository(session),
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
        NotificationAuditRepository(session), session_factory=request.app.state.db_session_factory
    )


AuditSvc = Annotated[AuditService, Depends(get_audit_service)]


def get_delivery_attempt_repository(session: DbSession) -> NotificationDeliveryAttemptRepository:
    """The current request's delivery attempt repository (read-only surface)."""
    return NotificationDeliveryAttemptRepository(session)


DeliveryAttemptRepo = Annotated[
    NotificationDeliveryAttemptRepository, Depends(get_delivery_attempt_repository)
]
