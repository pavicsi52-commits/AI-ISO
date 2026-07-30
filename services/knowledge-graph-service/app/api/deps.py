"""FastAPI dependency injection for the knowledge graph service.

One factory per business service, each building its own repositories
from the request-scoped session -- routes depend on services only.

**The Neo4j driver and graph client are process-wide**, built once by
the application factory. A per-request driver would open a new
connection pool on every query, which is the opposite of the connection
pooling docs/049 "PERFORMANCE" asks for.

**Synchronization uses a service token, not the caller's.** A sync runs
unattended with no caller present. That is a real departure from
``services/dashboard-service``, which reads every source as the asking
user, and it is why the sync dependency is separate from every other
one here -- see :mod:`app.clients.platform` for the consequence.
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
from shared_core.notifications.manager import NotificationManager
from shared_core.security.jwt import decode_token
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.platform import PlatformSourceClient, build_source_endpoints
from app.dependencies.engine import DependencyEngine
from app.digital_twin.twin import DigitalTwinService
from app.graph.client import GraphClient
from app.graph.repository import GraphRepository
from app.notifications.graph_notifications import GraphNotificationService
from app.repositories.graph_audit import GraphAuditRepository
from app.repositories.graph_change_history import GraphChangeHistoryRepository
from app.repositories.graph_export_job import GraphExportJobRepository
from app.repositories.graph_import_job import GraphImportJobRepository
from app.repositories.graph_metadata import GraphMetadataRepository
from app.repositories.graph_query import GraphQueryRepository
from app.repositories.graph_report import GraphReportRepository
from app.repositories.graph_saved_query import GraphSavedQueryRepository
from app.repositories.graph_snapshot import GraphSnapshotRepository
from app.repositories.graph_statistics import GraphStatisticsRepository
from app.repositories.graph_sync_job import GraphSyncJobRepository
from app.repositories.graph_version import GraphVersionRepository
from app.search.engine import SearchEngine
from app.services.analytics import AnalyticsService
from app.services.audit import AuditService
from app.services.graph import GraphService
from app.services.graph_io import GraphIoService
from app.services.query import QueryService
from app.services.statistics import StatisticsService
from app.services.sync import SyncService
from app.synchronization.engine import SynchronizationEngine
from app.types import EventPublisher
from app.versioning.snapshots import SnapshotService

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


def get_graph_client(request: Request) -> GraphClient:
    """The process-wide Neo4j client.

    Process-wide rather than per-request: a client built per request
    would open a new connection pool on every query.
    """
    return request.app.state.graph_client  # type: ignore[no-any-return]


GraphClientDep = Annotated[GraphClient, Depends(get_graph_client)]


def get_graph_repository(request: Request, client: GraphClientDep) -> GraphRepository:
    """The graph repository, bound to the process-wide client."""
    settings = request.app.state.service_settings
    return GraphRepository(
        client,
        max_depth=settings.max_traversal_depth,
        max_nodes=settings.max_result_nodes,
    )


GraphRepo = Annotated[GraphRepository, Depends(get_graph_repository)]


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
    """The raw Bearer token.

    Raises:
        AuthenticationError: If no valid Bearer token is presented.
    """
    if credentials is None:
        raise AuthenticationError("Authentication required.")
    return credentials.credentials


CurrentUserToken = Annotated[str, Depends(get_caller_token)]


def get_notification_service(
    manager: Annotated[NotificationManager, Depends(get_notification_manager)],
) -> GraphNotificationService:
    """The current request's notification service."""
    return GraphNotificationService(manager)


NotificationSvc = Annotated[GraphNotificationService, Depends(get_notification_service)]


def get_graph_service(
    session: DbSession, graph: GraphRepo, publish_event: EventPublisherDep
) -> GraphService:
    """The current request's graph service."""
    return GraphService(
        graph,
        GraphChangeHistoryRepository(session),
        GraphMetadataRepository(session),
        publish_event=publish_event,
    )


GraphSvc = Annotated[GraphService, Depends(get_graph_service)]


def get_query_service(request: Request, session: DbSession, client: GraphClientDep) -> QueryService:
    """The current request's query service."""
    settings = request.app.state.service_settings
    return QueryService(
        client,
        GraphQueryRepository(session),
        GraphSavedQueryRepository(session),
        allow_custom_cypher=settings.allow_custom_cypher,
        max_rows=settings.max_result_nodes,
    )


QuerySvc = Annotated[QueryService, Depends(get_query_service)]


def get_dependency_engine(request: Request, graph: GraphRepo) -> DependencyEngine:
    """The current request's dependency engine."""
    settings = request.app.state.service_settings
    return DependencyEngine(
        graph,
        max_depth=settings.max_traversal_depth,
        max_nodes=settings.max_result_nodes,
    )


def get_analytics_service(
    request: Request,
    session: DbSession,
    graph: GraphRepo,
    dependencies: Annotated[DependencyEngine, Depends(get_dependency_engine)],
    publish_event: EventPublisherDep,
) -> AnalyticsService:
    """The current request's analytics service."""
    settings = request.app.state.service_settings
    return AnalyticsService(
        graph,
        GraphReportRepository(session),
        GraphMetadataRepository(session),
        dependencies,
        publish_event=publish_event,
        max_nodes=settings.analytics_max_nodes,
        pagerank_iterations=settings.pagerank_iterations,
        pagerank_damping=settings.pagerank_damping,
    )


AnalyticsSvc = Annotated[AnalyticsService, Depends(get_analytics_service)]


def get_twin_service(session: DbSession, graph: GraphRepo) -> DigitalTwinService:
    """The current request's digital twin service."""
    return DigitalTwinService(graph, GraphMetadataRepository(session))


TwinSvc = Annotated[DigitalTwinService, Depends(get_twin_service)]


def get_snapshot_service(request: Request, session: DbSession, graph: GraphRepo) -> SnapshotService:
    """The current request's snapshot service."""
    settings = request.app.state.service_settings
    return SnapshotService(
        graph,
        GraphSnapshotRepository(session),
        GraphVersionRepository(session),
        retention_days=settings.snapshot_retention_days,
    )


SnapshotSvc = Annotated[SnapshotService, Depends(get_snapshot_service)]


def get_search_engine(session: DbSession, client: GraphClientDep) -> SearchEngine:
    """The current request's search engine."""
    return SearchEngine(client, GraphMetadataRepository(session))


SearchSvc = Annotated[SearchEngine, Depends(get_search_engine)]


def get_io_service(
    request: Request,
    session: DbSession,
    graph: GraphRepo,
    notifications: NotificationSvc,
) -> GraphIoService:
    """The current request's import/export service."""
    settings = request.app.state.service_settings
    return GraphIoService(
        graph,
        GraphImportJobRepository(session),
        GraphExportJobRepository(session),
        notifications,
        max_import_nodes=settings.max_import_nodes,
        max_export_nodes=settings.max_export_nodes,
    )


IoSvc = Annotated[GraphIoService, Depends(get_io_service)]


def get_sync_service(
    request: Request,
    session: DbSession,
    graph: GraphRepo,
    snapshots: SnapshotSvc,
    notifications: NotificationSvc,
    publish_event: EventPublisherDep,
) -> SyncService:
    """The current request's synchronization service.

    Bound to a **service token**, not the caller's. A sync runs
    unattended; there is no caller token at 03:00. See
    :mod:`app.clients.platform` for what that means for what the
    mappers are allowed to project.
    """
    settings = request.app.state.service_settings
    sources = PlatformSourceClient(
        request.app.state.http_client,
        build_source_endpoints(settings),
        service_token=request.app.state.service_token,
        page_size=settings.sync_batch_size,
    )
    engine = SynchronizationEngine(
        graph,
        GraphSyncJobRepository(session),
        GraphChangeHistoryRepository(session),
        GraphMetadataRepository(session),
        sources,
        batch_size=settings.sync_batch_size,
        max_failures=settings.sync_max_failures,
    )
    return SyncService(
        engine,
        GraphSyncJobRepository(session),
        snapshots,
        notifications,
        publish_event=publish_event,
    )


SyncSvc = Annotated[SyncService, Depends(get_sync_service)]


def get_statistics_service(
    request: Request, session: DbSession, graph: GraphRepo, twins: TwinSvc
) -> StatisticsService:
    """The current request's statistics service."""
    settings = request.app.state.service_settings
    return StatisticsService(
        graph,
        GraphStatisticsRepository(session),
        GraphMetadataRepository(session),
        GraphSyncJobRepository(session),
        twins,
        max_nodes=settings.analytics_max_nodes,
    )


StatisticsSvc = Annotated[StatisticsService, Depends(get_statistics_service)]


def get_audit_service(request: Request, session: DbSession) -> AuditService:
    """The current request's audit service.

    Given the application's session factory as well as the request's
    session, so ``record_denied`` can commit in a transaction of its
    own. A refusal is recorded and then *raised*, and the raise rolls
    the request transaction back -- so a DENIED entry written on the
    shared session never survives the request that produced it.
    """
    return AuditService(
        GraphAuditRepository(session),
        session_factory=request.app.state.db_session_factory,
    )


AuditSvc = Annotated[AuditService, Depends(get_audit_service)]


__all__ = [
    "AnalyticsSvc",
    "AuditSvc",
    "CurrentUserId",
    "CurrentUserToken",
    "DbSession",
    "EventPublisherDep",
    "GraphClientDep",
    "GraphRepo",
    "GraphSvc",
    "IoSvc",
    "NotificationSvc",
    "QuerySvc",
    "SearchSvc",
    "SnapshotSvc",
    "StatisticsSvc",
    "SyncSvc",
    "TwinSvc",
    "get_analytics_service",
    "get_audit_service",
    "get_caller_token",
    "get_current_user_id",
    "get_db_session",
    "get_dependency_engine",
    "get_event_publisher",
    "get_graph_client",
    "get_graph_repository",
    "get_graph_service",
    "get_http_client",
    "get_io_service",
    "get_notification_manager",
    "get_notification_service",
    "get_query_service",
    "get_search_engine",
    "get_snapshot_service",
    "get_statistics_service",
    "get_sync_service",
    "get_twin_service",
]
