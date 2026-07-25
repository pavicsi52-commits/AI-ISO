"""FastAPI dependency injection for the discovery service.

One factory function per business service, each building its own
repositories from the request-scoped database session -- routes depend
on services only, never repositories directly. Matches
``services/inventory-service/app/api/deps.py``'s established shape,
with the addition of :func:`get_caller_token` (this service's own
downstream calls -- credential resolution, Inventory Service sync --
need the raw Bearer token, not just the decoded user id) and
:func:`get_scheduler_manager` (the first AI-IOS service to register
live schedules with ``shared_core.scheduler``).
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
from shared_core.queue.producer import Producer
from shared_core.scheduler import JobFn, SchedulerManager
from shared_core.security.jwt import decode_token
from sqlalchemy.ext.asyncio import AsyncSession

from app.discovery.credentials import CredentialResolver
from app.discovery.inventory_sync import InventorySyncClient
from app.notifications.discovery_notifications import DiscoveryNotificationService
from app.repositories.discovery_asset import DiscoveryAssetRepository
from app.repositories.discovery_audit import DiscoveryAuditRepository
from app.repositories.discovery_classification import DiscoveryClassificationRepository
from app.repositories.discovery_credential import DiscoveryCredentialRepository
from app.repositories.discovery_failure import DiscoveryFailureRepository
from app.repositories.discovery_history import DiscoveryHistoryRepository
from app.repositories.discovery_job import DiscoveryJobRepository
from app.repositories.discovery_profile import DiscoveryProfileRepository
from app.repositories.discovery_relationship import DiscoveryRelationshipRepository
from app.repositories.discovery_result import DiscoveryResultRepository
from app.repositories.discovery_rule import DiscoveryRuleRepository
from app.repositories.discovery_schedule import DiscoveryScheduleRepository
from app.repositories.discovery_statistics import DiscoveryStatisticsRepository
from app.repositories.discovery_target import DiscoveryTargetRepository
from app.services.asset import DiscoveryAssetService
from app.services.audit import DiscoveryAuditService
from app.services.classification import DiscoveryClassificationService
from app.services.credential import DiscoveryCredentialService
from app.services.discovery_execution import DiscoveryExecutionService
from app.services.failure import DiscoveryFailureService
from app.services.history import DiscoveryHistoryService
from app.services.job import DiscoveryJobService
from app.services.profile import DiscoveryProfileService
from app.services.relationship import DiscoveryRelationshipService
from app.services.result import DiscoveryResultService
from app.services.rule import DiscoveryRuleService
from app.services.schedule import DiscoveryScheduleService
from app.services.statistics import DiscoveryStatisticsService
from app.services.target import DiscoveryTargetService

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped database session, committing on success.

    Per docs/018 "Transaction Session" -- see the identical rationale in
    every prior AI-IOS service's own ``get_db_session``.
    """
    session_factory = request.app.state.db_session_factory
    async with session_scope(session_factory) as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db_session)]


def get_notification_manager(request: Request) -> NotificationManager:
    """The process-wide :class:`NotificationManager`."""
    return request.app.state.notification_manager  # type: ignore[no-any-return]


def get_queue_producer(request: Request) -> Producer:
    """The process-wide queue :class:`Producer`, for enqueueing discovery jobs."""
    return request.app.state.queue_producer  # type: ignore[no-any-return]


def get_scheduler_manager(request: Request) -> SchedulerManager:
    """The process-wide :class:`SchedulerManager`."""
    return request.app.state.scheduler_manager  # type: ignore[no-any-return]


def get_discovery_schedule_fn(request: Request) -> JobFn:
    """The process-wide callback every registered
    :class:`~app.models.discovery_schedule.DiscoverySchedule` fires when
    due -- built once in ``app/core/factory.py``'s ``_lifespan`` (it
    closes over the database session factory and queue producer, neither
    of which is request-scoped), reused by every
    ``app/api/schedule.py`` create/update handler so a schedule starts
    firing immediately rather than only after the next process restart.
    """
    return request.app.state.discovery_schedule_fn  # type: ignore[no-any-return]


def get_http_client(request: Request) -> httpx.AsyncClient:
    """The process-wide :class:`httpx.AsyncClient` shared by every
    cross-service call this service makes (Secrets Management Service
    credential resolution, Inventory Service synchronization).
    """
    return request.app.state.http_client  # type: ignore[no-any-return]


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


async def get_caller_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
) -> str:
    """The raw Bearer token string, forwarded to the Secrets Management
    Service and the Inventory Service on this caller's behalf -- see
    ``app/discovery/credentials.py``/``app/discovery/inventory_sync.py``.

    Raises:
        AuthenticationError: If no valid Bearer token is presented.
    """
    if credentials is None:
        raise AuthenticationError("Authentication required.")
    return credentials.credentials


CurrentUserToken = Annotated[str, Depends(get_caller_token)]


def get_notification_service(
    manager: Annotated[NotificationManager, Depends(get_notification_manager)],
) -> DiscoveryNotificationService:
    """The current request's :class:`DiscoveryNotificationService`."""
    return DiscoveryNotificationService(manager)


def get_credential_resolver(
    client: Annotated[httpx.AsyncClient, Depends(get_http_client)], request: Request
) -> CredentialResolver:
    """The current request's :class:`CredentialResolver`."""
    settings = request.app.state.service_settings
    return CredentialResolver(client, base_url=settings.secrets_service_base_url)


def get_inventory_sync_client(
    client: Annotated[httpx.AsyncClient, Depends(get_http_client)], request: Request
) -> InventorySyncClient:
    """The current request's :class:`InventorySyncClient`."""
    settings = request.app.state.service_settings
    return InventorySyncClient(client, base_url=settings.inventory_service_base_url)


def get_profile_service(request: Request, session: DbSession) -> DiscoveryProfileService:
    """The current request's :class:`DiscoveryProfileService`."""
    return DiscoveryProfileService(
        DiscoveryProfileRepository(session),
        publish_event=getattr(request.app.state, "publish_event", None),
    )


ProfileSvc = Annotated[DiscoveryProfileService, Depends(get_profile_service)]


def get_target_service(session: DbSession) -> DiscoveryTargetService:
    """The current request's :class:`DiscoveryTargetService`."""
    return DiscoveryTargetService(DiscoveryTargetRepository(session))


TargetSvc = Annotated[DiscoveryTargetService, Depends(get_target_service)]


def get_credential_service(session: DbSession) -> DiscoveryCredentialService:
    """The current request's :class:`DiscoveryCredentialService`."""
    return DiscoveryCredentialService(DiscoveryCredentialRepository(session))


CredentialSvc = Annotated[DiscoveryCredentialService, Depends(get_credential_service)]


def get_schedule_service(session: DbSession) -> DiscoveryScheduleService:
    """The current request's :class:`DiscoveryScheduleService`."""
    return DiscoveryScheduleService(DiscoveryScheduleRepository(session))


ScheduleSvc = Annotated[DiscoveryScheduleService, Depends(get_schedule_service)]


def get_history_service(session: DbSession) -> DiscoveryHistoryService:
    """The current request's :class:`DiscoveryHistoryService`."""
    return DiscoveryHistoryService(DiscoveryHistoryRepository(session))


HistorySvc = Annotated[DiscoveryHistoryService, Depends(get_history_service)]


def get_failure_service(session: DbSession) -> DiscoveryFailureService:
    """The current request's :class:`DiscoveryFailureService`."""
    return DiscoveryFailureService(DiscoveryFailureRepository(session))


FailureSvc = Annotated[DiscoveryFailureService, Depends(get_failure_service)]


def get_audit_service(session: DbSession) -> DiscoveryAuditService:
    """The current request's :class:`DiscoveryAuditService`."""
    return DiscoveryAuditService(DiscoveryAuditRepository(session))


AuditSvc = Annotated[DiscoveryAuditService, Depends(get_audit_service)]


def get_result_service(session: DbSession) -> DiscoveryResultService:
    """The current request's :class:`DiscoveryResultService`."""
    return DiscoveryResultService(DiscoveryResultRepository(session))


ResultSvc = Annotated[DiscoveryResultService, Depends(get_result_service)]


def get_asset_service(
    request: Request,
    session: DbSession,
    inventory_sync: Annotated[InventorySyncClient, Depends(get_inventory_sync_client)],
) -> DiscoveryAssetService:
    """The current request's :class:`DiscoveryAssetService`."""
    return DiscoveryAssetService(
        DiscoveryAssetRepository(session),
        inventory_sync,
        publish_event=getattr(request.app.state, "publish_event", None),
    )


AssetSvc = Annotated[DiscoveryAssetService, Depends(get_asset_service)]


def get_relationship_service(
    request: Request,
    session: DbSession,
    inventory_sync: Annotated[InventorySyncClient, Depends(get_inventory_sync_client)],
) -> DiscoveryRelationshipService:
    """The current request's :class:`DiscoveryRelationshipService`."""
    return DiscoveryRelationshipService(
        DiscoveryRelationshipRepository(session),
        inventory_sync,
        publish_event=getattr(request.app.state, "publish_event", None),
    )


RelationshipSvc = Annotated[DiscoveryRelationshipService, Depends(get_relationship_service)]


def get_statistics_service(session: DbSession) -> DiscoveryStatisticsService:
    """The current request's :class:`DiscoveryStatisticsService`."""
    return DiscoveryStatisticsService(
        DiscoveryStatisticsRepository(session),
        DiscoveryJobRepository(session),
        DiscoveryAssetRepository(session),
        DiscoveryRelationshipRepository(session),
        DiscoveryFailureRepository(session),
    )


StatisticsSvc = Annotated[DiscoveryStatisticsService, Depends(get_statistics_service)]


def get_job_service(request: Request, session: DbSession) -> DiscoveryJobService:
    """The current request's :class:`DiscoveryJobService`."""
    return DiscoveryJobService(
        DiscoveryJobRepository(session),
        DiscoveryTargetRepository(session),
        session,
        publish_event=getattr(request.app.state, "publish_event", None),
    )


JobSvc = Annotated[DiscoveryJobService, Depends(get_job_service)]


def get_execution_service(
    request: Request,
    session: DbSession,
    jobs: JobSvc,
    targets: TargetSvc,
    credentials: CredentialSvc,
    results: ResultSvc,
    assets: AssetSvc,
    relationships: RelationshipSvc,
    failures: FailureSvc,
    history: HistorySvc,
    audit: AuditSvc,
    credential_resolver: Annotated[CredentialResolver, Depends(get_credential_resolver)],
) -> DiscoveryExecutionService:
    """The current request's fully-wired :class:`DiscoveryExecutionService`.

    Exposed for completeness/tests -- interactive requests only ever
    *queue* a job (see ``app/api/job.py``/``app/api/scan.py``); the
    actual execution always runs inside
    ``app/workers/discovery_worker.py``'s own session-scoped instance.

    ``DiscoveryRuleService``/``DiscoveryClassificationService`` are
    built inline here rather than exposed as their own public ``Svc``
    aliases -- like ``DiscoveryRuleService`` itself, neither has a REST
    surface of its own (see each one's own module docstring); this
    execution engine is their only caller.
    """
    return DiscoveryExecutionService(
        jobs,
        targets,
        credentials,
        results,
        assets,
        relationships,
        failures,
        history,
        audit,
        credential_resolver,
        DiscoveryRuleService(DiscoveryRuleRepository(session)),
        DiscoveryClassificationService(DiscoveryClassificationRepository(session)),
        publish_event=getattr(request.app.state, "publish_event", None),
    )


ExecutionSvc = Annotated[DiscoveryExecutionService, Depends(get_execution_service)]


__all__ = [
    "AssetSvc",
    "AuditSvc",
    "CredentialSvc",
    "CurrentUserId",
    "CurrentUserToken",
    "DbSession",
    "ExecutionSvc",
    "FailureSvc",
    "HistorySvc",
    "JobSvc",
    "ProfileSvc",
    "RelationshipSvc",
    "ResultSvc",
    "ScheduleSvc",
    "StatisticsSvc",
    "TargetSvc",
    "get_asset_service",
    "get_audit_service",
    "get_caller_token",
    "get_credential_resolver",
    "get_credential_service",
    "get_current_user_id",
    "get_db_session",
    "get_discovery_schedule_fn",
    "get_execution_service",
    "get_failure_service",
    "get_history_service",
    "get_http_client",
    "get_inventory_sync_client",
    "get_job_service",
    "get_notification_manager",
    "get_notification_service",
    "get_profile_service",
    "get_queue_producer",
    "get_relationship_service",
    "get_result_service",
    "get_schedule_service",
    "get_scheduler_manager",
    "get_statistics_service",
    "get_target_service",
]
