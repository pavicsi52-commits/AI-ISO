"""FastAPI dependency injection for the dashboard service.

One factory per business service, each building its own repositories
from the request-scoped session -- routes depend on services only.

As in ``services/reporting-service`` and
``services/ai-assistant-service``, the widget resolver needs the
**caller's own bearer token**, because every data source a dashboard
reads is read as the asking user. That is what keeps RBAC enforced by
the service owning the data rather than reimplemented here, and it is
why :data:`CurrentUserToken` exists alongside :data:`CurrentUserId`.

The hub, the broadcaster, and the Neo4j driver are **process-wide**,
built once by the application factory: a per-request hub would give
every connection its own empty set of subscribers, and a per-request
Neo4j driver would open a new connection pool on every topology widget.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

import httpx
from fastapi import Depends, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from shared_core.database.session import session_scope
from shared_core.exceptions.authentication import AuthenticationError
from shared_core.notifications.manager import NotificationManager
from shared_core.security.jwt import decode_token
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.platform import PlatformSourceClient, build_source_endpoints
from app.notifications.dashboard_notifications import DashboardNotificationService
from app.realtime.hub import DashboardHub
from app.repositories.dashboard import DashboardRepository
from app.repositories.dashboard_audit import DashboardAuditRepository
from app.repositories.dashboard_favorite import DashboardFavoriteRepository
from app.repositories.dashboard_filter import DashboardFilterRepository
from app.repositories.dashboard_history import DashboardHistoryRepository
from app.repositories.dashboard_layout import DashboardLayoutRepository
from app.repositories.dashboard_permission import DashboardPermissionRepository
from app.repositories.dashboard_share import DashboardShareRepository
from app.repositories.dashboard_statistics import DashboardStatisticsRepository
from app.repositories.dashboard_template import DashboardTemplateRepository
from app.repositories.dashboard_theme import DashboardThemeRepository
from app.repositories.dashboard_view import DashboardViewRepository
from app.repositories.dashboard_widget import DashboardWidgetRepository
from app.repositories.dashboard_widget_setting import DashboardWidgetSettingRepository
from app.services.audit import AuditService
from app.services.dashboard import DashboardService
from app.services.preferences import PreferencesService
from app.services.sharing import SharingService
from app.services.statistics import StatisticsService
from app.services.streaming import StreamingService
from app.services.template import TemplateService
from app.services.theme import ThemeService
from app.topology.graph import TopologyReader
from app.types import EventPublisher
from app.widgets.resolver import WidgetResolver

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped database session, committing on success."""
    session_factory = request.app.state.db_session_factory
    async with session_scope(session_factory) as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db_session)]


def get_http_client(request: Request) -> httpx.AsyncClient:
    """The process-wide HTTP client shared by every outbound call."""
    return request.app.state.http_client  # type: ignore[no-any-return]


def get_event_publisher(request: Request) -> EventPublisher:
    """The process-wide domain-event publisher."""
    return request.app.state.publish_event  # type: ignore[no-any-return]


EventPublisherDep = Annotated[EventPublisher, Depends(get_event_publisher)]


def get_notification_manager(request: Request) -> NotificationManager:
    """The process-wide notification manager."""
    return request.app.state.notification_manager  # type: ignore[no-any-return]


def get_hub(request: Request) -> DashboardHub:
    """The process-wide real-time hub.

    Process-wide rather than per-request: a hub built per request would
    hold no subscribers but the one that just connected, so nothing
    would ever be delivered.
    """
    return request.app.state.hub  # type: ignore[no-any-return]


def get_topology_reader(request: Request) -> TopologyReader:
    """The process-wide topology reader.

    Always present. When Neo4j is unconfigured it reports itself
    disabled, which the resolver turns into a failed *widget* rather
    than a failed dashboard.
    """
    return request.app.state.topology  # type: ignore[no-any-return]


TopologyDep = Annotated[TopologyReader, Depends(get_topology_reader)]


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


async def get_caller_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
) -> str:
    """The raw Bearer token, forwarded to every data source.

    Raises:
        AuthenticationError: If no valid Bearer token is presented.
    """
    if credentials is None:
        raise AuthenticationError("Authentication required.")
    return credentials.credentials


CurrentUserToken = Annotated[str, Depends(get_caller_token)]


async def get_optional_caller_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
) -> str | None:
    """The caller's Bearer token if they presented one, else ``None``.

    Exists for the share-link route, which is genuinely reachable
    without a session -- the token in the URL *is* the credential for
    getting at the dashboard. Depending on :data:`CurrentUserToken`
    there would make that route require a login, silently turning a
    documented feature off; that is exactly how it first shipped, and
    the test suite catches it now.
    """
    return credentials.credentials if credentials is not None else None


OptionalUserToken = Annotated[str | None, Depends(get_optional_caller_token)]


async def get_caller_roles(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
) -> list[str]:
    """The roles claimed by the caller's token.

    Read from the *verified* token rather than a header, so a caller
    cannot grant themselves a role by editing a request. A token with no
    roles claim yields an empty list, which the sharing service treats
    as "no role-based grants" rather than as an error.
    """
    if credentials is None:
        raise AuthenticationError("Authentication required.")
    claims = decode_token(credentials.credentials, public_key=request.app.state.jwt_public_key)
    raw = claims.get("roles") or []
    return [str(role) for role in raw] if isinstance(raw, list) else []


CallerRoles = Annotated[list[str], Depends(get_caller_roles)]


def get_source_client(
    request: Request,
    http_client: Annotated[httpx.AsyncClient, Depends(get_http_client)],
    caller_token: CurrentUserToken,
) -> PlatformSourceClient:
    """A data-source client bound to *this caller's own* token."""
    settings = request.app.state.service_settings
    return PlatformSourceClient(
        http_client,
        build_source_endpoints(settings),
        caller_token=caller_token,
        max_rows=settings.max_rows_per_widget,
    )


def get_resolver(
    request: Request,
    sources: Annotated[PlatformSourceClient, Depends(get_source_client)],
    topology: TopologyDep,
) -> WidgetResolver:
    """The current request's fully-wired widget resolver."""
    settings = request.app.state.service_settings
    return WidgetResolver(
        sources,
        topology,
        getattr(request.app.state, "ai_client", None),
        max_parallel=settings.max_parallel_widgets,
        max_rows=settings.max_rows_per_widget,
    )


def get_dashboard_service(
    request: Request,
    session: DbSession,
    resolver: Annotated[WidgetResolver, Depends(get_resolver)],
    publish_event: EventPublisherDep,
) -> DashboardService:
    """The current request's dashboard service."""
    settings = request.app.state.service_settings
    return DashboardService(
        DashboardRepository(session),
        DashboardWidgetRepository(session),
        DashboardLayoutRepository(session),
        DashboardHistoryRepository(session),
        DashboardViewRepository(session),
        resolver,
        publish_event=publish_event,
        max_widgets=settings.max_widgets_per_dashboard,
    )


DashboardSvc = Annotated[DashboardService, Depends(get_dashboard_service)]


def get_link_dashboard_service(
    request: Request,
    session: DbSession,
    topology: TopologyDep,
    caller_token: OptionalUserToken,
    publish_event: EventPublisherDep,
) -> DashboardService:
    """A dashboard service for the share-link route.

    A signed-in visitor following a link gets their widgets resolved
    with **their own** token, exactly as any other request would. An
    anonymous visitor gets the dashboard's structure with every widget
    marked ``UNAUTHORIZED``: this service holds no credential of its
    own, so there is nothing it could honestly resolve the data with.
    Resolving under the *sharer's* rights would silently hand a
    stranger whatever that person can see.
    """
    settings = request.app.state.service_settings
    sources = (
        PlatformSourceClient(
            request.app.state.http_client,
            build_source_endpoints(settings),
            caller_token=caller_token,
            max_rows=settings.max_rows_per_widget,
        )
        if caller_token is not None
        else None
    )
    return DashboardService(
        DashboardRepository(session),
        DashboardWidgetRepository(session),
        DashboardLayoutRepository(session),
        DashboardHistoryRepository(session),
        DashboardViewRepository(session),
        WidgetResolver(
            sources,
            topology,
            None,
            max_parallel=settings.max_parallel_widgets,
            max_rows=settings.max_rows_per_widget,
            anonymous=sources is None,
        ),
        publish_event=publish_event,
        max_widgets=settings.max_widgets_per_dashboard,
    )


LinkDashboardSvc = Annotated[DashboardService, Depends(get_link_dashboard_service)]


def get_sharing_service(
    request: Request, session: DbSession, publish_event: EventPublisherDep
) -> SharingService:
    """The current request's sharing and access-control service."""
    settings = request.app.state.service_settings
    return SharingService(
        DashboardRepository(session),
        DashboardShareRepository(session),
        DashboardPermissionRepository(session),
        publish_event=publish_event,
        link_ttl_seconds=settings.share_link_ttl_seconds,
    )


SharingSvc = Annotated[SharingService, Depends(get_sharing_service)]


def get_theme_service(session: DbSession) -> ThemeService:
    """The current request's theme service."""
    return ThemeService(DashboardThemeRepository(session))


ThemeSvc = Annotated[ThemeService, Depends(get_theme_service)]


def get_template_service(session: DbSession, dashboards: DashboardSvc) -> TemplateService:
    """The current request's template service."""
    return TemplateService(DashboardTemplateRepository(session), dashboards)


TemplateSvc = Annotated[TemplateService, Depends(get_template_service)]


def get_preferences_service(session: DbSession) -> PreferencesService:
    """The current request's preferences service."""
    return PreferencesService(
        DashboardRepository(session),
        DashboardWidgetRepository(session),
        DashboardFavoriteRepository(session),
        DashboardFilterRepository(session),
        DashboardWidgetSettingRepository(session),
    )


PreferencesSvc = Annotated[PreferencesService, Depends(get_preferences_service)]


def get_statistics_service(session: DbSession) -> StatisticsService:
    """The current request's analytics service."""
    return StatisticsService(
        DashboardRepository(session),
        DashboardWidgetRepository(session),
        DashboardViewRepository(session),
        DashboardShareRepository(session),
        DashboardStatisticsRepository(session),
    )


StatisticsSvc = Annotated[StatisticsService, Depends(get_statistics_service)]


def get_audit_service(session: DbSession) -> AuditService:
    """The current request's audit service."""
    return AuditService(DashboardAuditRepository(session))


AuditSvc = Annotated[AuditService, Depends(get_audit_service)]


def get_streaming_service(
    hub: Annotated[DashboardHub, Depends(get_hub)], dashboards: DashboardSvc
) -> StreamingService:
    """The current request's streaming service."""
    return StreamingService(hub, dashboards)


StreamingSvc = Annotated[StreamingService, Depends(get_streaming_service)]


def get_notification_service(
    manager: Annotated[NotificationManager, Depends(get_notification_manager)],
) -> DashboardNotificationService:
    """The current request's notification service."""
    return DashboardNotificationService(manager)


NotificationSvc = Annotated[DashboardNotificationService, Depends(get_notification_service)]

DashboardIdQuery = Annotated[
    UUID,
    Query(
        description=(
            "The dashboard these widgets or layouts belong to. Required: "
            "widgets and layouts have no meaning outside one dashboard."
        )
    ),
]
"""The ``dashboard_id`` query parameter the collection routes require.

docs/048 specifies ``GET /dashboards/widgets`` and
``GET /dashboards/layouts`` as flat collections. They are scoped by
this parameter rather than returning every widget in the organization,
which would be both a large response and a cross-dashboard leak.
"""


__all__ = [
    "AuditSvc",
    "CallerRoles",
    "CurrentUserId",
    "CurrentUserToken",
    "DashboardIdQuery",
    "DashboardSvc",
    "DbSession",
    "EventPublisherDep",
    "LinkDashboardSvc",
    "NotificationSvc",
    "OptionalUserToken",
    "PreferencesSvc",
    "SharingSvc",
    "StatisticsSvc",
    "StreamingSvc",
    "TemplateSvc",
    "ThemeSvc",
    "TopologyDep",
    "get_audit_service",
    "get_caller_roles",
    "get_caller_token",
    "get_current_user_id",
    "get_dashboard_service",
    "get_db_session",
    "get_event_publisher",
    "get_http_client",
    "get_hub",
    "get_link_dashboard_service",
    "get_notification_manager",
    "get_notification_service",
    "get_optional_caller_token",
    "get_preferences_service",
    "get_resolver",
    "get_sharing_service",
    "get_source_client",
    "get_statistics_service",
    "get_streaming_service",
    "get_template_service",
    "get_theme_service",
    "get_topology_reader",
]
