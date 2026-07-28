"""FastAPI dependency injection for the reporting service.

One factory per business service, each building its own repositories
from the request-scoped session -- routes depend on services only.

As in ``services/ai-assistant-service``, several dependencies need the
**caller's own bearer token**, because every data source a report reads
is read as the asking user. That is what keeps RBAC enforced by the
service owning the data rather than reimplemented here, and it is why
:data:`CurrentUserToken` exists alongside :data:`CurrentUserId`.
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
from shared_core.storage.wrapper import StorageWrapper
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.summaries import AiSummaryClient
from app.clients.platform import PlatformSourceClient, SourceEndpoints
from app.distribution.channels import DistributionDispatcher
from app.notifications.report_notifications import ReportNotificationService
from app.renderer.engine import ReportRenderer
from app.repositories.report_archive import ReportArchiveRepository
from app.repositories.report_audit import ReportAuditRepository
from app.repositories.report_category import ReportCategoryRepository
from app.repositories.report_distribution import ReportDistributionRepository
from app.repositories.report_execution import ReportExecutionRepository
from app.repositories.report_export import ReportExportRepository
from app.repositories.report_favorite import ReportFavoriteRepository
from app.repositories.report_history import ReportHistoryRepository
from app.repositories.report_job import ReportJobRepository
from app.repositories.report_parameter import ReportParameterRepository
from app.repositories.report_recipient import ReportRecipientRepository
from app.repositories.report_schedule import ReportScheduleRepository
from app.repositories.report_statistics import ReportStatisticsRepository
from app.repositories.report_template import ReportTemplateRepository
from app.services.archive import ReportArchiveService
from app.services.audit import ReportAuditService
from app.services.distribution import ReportDistributionService
from app.services.generation import ReportGenerationService
from app.services.job import ReportJobService
from app.services.schedule import ReportScheduleService
from app.services.statistics import ReportStatisticsService
from app.services.template import ReportTemplateService
from app.types import EventPublisher

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


def get_storage(request: Request) -> StorageWrapper | None:
    """The process-wide object-storage wrapper, if configured.

    ``None`` is not a failure: object storage is one distribution
    channel among six, and a deployment without MinIO simply reports
    that channel unavailable rather than failing to start.
    """
    return getattr(request.app.state, "storage", None)


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


def get_source_client(
    request: Request,
    http_client: Annotated[httpx.AsyncClient, Depends(get_http_client)],
    caller_token: CurrentUserToken,
) -> PlatformSourceClient:
    """A data-source client bound to *this caller's own* token."""
    settings = request.app.state.service_settings
    return PlatformSourceClient(
        http_client,
        SourceEndpoints(
            inventory=settings.inventory_service_base_url,
            discovery=settings.discovery_service_base_url,
            configuration=settings.configuration_service_base_url,
            automation=settings.automation_service_base_url,
            workflow=settings.workflow_runtime_service_base_url,
            validation=settings.validation_service_base_url,
            monitoring=settings.monitoring_service_base_url,
            alerting=settings.alerting_service_base_url,
            ai_assistant=settings.ai_assistant_service_base_url,
            compliance=settings.compliance_service_base_url,
            incident=settings.incident_service_base_url,
            administration=settings.administration_service_base_url,
        ),
        caller_token=caller_token,
        max_rows=settings.max_rows_per_report,
    )


def get_renderer(
    request: Request,
    sources: Annotated[PlatformSourceClient, Depends(get_source_client)],
    http_client: Annotated[httpx.AsyncClient, Depends(get_http_client)],
    caller_token: CurrentUserToken,
) -> ReportRenderer:
    """The current request's fully-wired renderer."""
    settings = request.app.state.service_settings
    return ReportRenderer(
        sources,
        AiSummaryClient(
            http_client,
            base_url=settings.ai_assistant_service_base_url,
            caller_token=caller_token,
            enabled=settings.ai_reporting_enabled,
        ),
        max_parallel_sections=settings.max_parallel_sections,
        max_rows=settings.max_rows_per_report,
    )


def get_template_service(session: DbSession) -> ReportTemplateService:
    """The current request's template service."""
    return ReportTemplateService(
        ReportTemplateRepository(session), ReportParameterRepository(session)
    )


TemplateSvc = Annotated[ReportTemplateService, Depends(get_template_service)]


def get_job_service(session: DbSession, publish_event: EventPublisherDep) -> ReportJobService:
    """The current request's saved-report service."""
    return ReportJobService(
        ReportJobRepository(session),
        ReportHistoryRepository(session),
        ReportFavoriteRepository(session),
        publish_event=publish_event,
    )


JobSvc = Annotated[ReportJobService, Depends(get_job_service)]


def get_generation_service(
    session: DbSession,
    templates: TemplateSvc,
    renderer: Annotated[ReportRenderer, Depends(get_renderer)],
    publish_event: EventPublisherDep,
) -> ReportGenerationService:
    """The current request's generation pipeline."""
    return ReportGenerationService(
        ReportJobRepository(session),
        ReportExecutionRepository(session),
        ReportExportRepository(session),
        ReportHistoryRepository(session),
        templates,
        renderer,
        publish_event=publish_event,
    )


GenerationSvc = Annotated[ReportGenerationService, Depends(get_generation_service)]


def get_distribution_service(
    request: Request,
    session: DbSession,
    http_client: Annotated[httpx.AsyncClient, Depends(get_http_client)],
    notifications: Annotated[NotificationManager, Depends(get_notification_manager)],
    storage: Annotated[StorageWrapper | None, Depends(get_storage)],
    publish_event: EventPublisherDep,
) -> ReportDistributionService:
    """The current request's distribution service."""
    settings = request.app.state.service_settings
    return ReportDistributionService(
        ReportDistributionRepository(session),
        ReportRecipientRepository(session),
        ReportExportRepository(session),
        DistributionDispatcher(
            http_client,
            notifications,
            storage,
            bucket=settings.object_storage_bucket,
            share_link_ttl_seconds=settings.share_link_ttl_seconds,
            webhook_timeout_seconds=settings.webhook_timeout_seconds,
        ),
        publish_event=publish_event,
    )


DistributionSvc = Annotated[ReportDistributionService, Depends(get_distribution_service)]


def get_schedule_service(
    session: DbSession, publish_event: EventPublisherDep
) -> ReportScheduleService:
    """The current request's schedule service."""
    return ReportScheduleService(ReportScheduleRepository(session), publish_event=publish_event)


ScheduleSvc = Annotated[ReportScheduleService, Depends(get_schedule_service)]


def get_archive_service(
    request: Request, session: DbSession, publish_event: EventPublisherDep
) -> ReportArchiveService:
    """The current request's archive service."""
    settings = request.app.state.service_settings
    return ReportArchiveService(
        ReportArchiveRepository(session),
        ReportExportRepository(session),
        publish_event=publish_event,
        retention_days=settings.archive_retention_days,
    )


ArchiveSvc = Annotated[ReportArchiveService, Depends(get_archive_service)]


def get_statistics_service(session: DbSession) -> ReportStatisticsService:
    """The current request's analytics service."""
    return ReportStatisticsService(
        ReportStatisticsRepository(session),
        ReportJobRepository(session),
        ReportExecutionRepository(session),
        ReportExportRepository(session),
        ReportDistributionRepository(session),
        ReportScheduleRepository(session),
        ReportTemplateRepository(session),
    )


StatisticsSvc = Annotated[ReportStatisticsService, Depends(get_statistics_service)]


def get_audit_service(session: DbSession) -> ReportAuditService:
    """The current request's audit service."""
    return ReportAuditService(ReportAuditRepository(session))


AuditSvc = Annotated[ReportAuditService, Depends(get_audit_service)]


def get_category_repository(session: DbSession) -> ReportCategoryRepository:
    """The current request's category repository.

    Categories are plain reference data with no behaviour beyond CRUD,
    so they get a repository dependency rather than a service that
    would only forward calls.
    """
    return ReportCategoryRepository(session)


CategoryRepo = Annotated[ReportCategoryRepository, Depends(get_category_repository)]


def get_export_repository(session: DbSession) -> ReportExportRepository:
    """The current request's export repository, for downloads."""
    return ReportExportRepository(session)


ExportRepo = Annotated[ReportExportRepository, Depends(get_export_repository)]


def get_execution_repository(session: DbSession) -> ReportExecutionRepository:
    """The current request's execution repository."""
    return ReportExecutionRepository(session)


ExecutionRepo = Annotated[ReportExecutionRepository, Depends(get_execution_repository)]


def get_notification_service(
    manager: Annotated[NotificationManager, Depends(get_notification_manager)],
) -> ReportNotificationService:
    """The current request's notification service."""
    return ReportNotificationService(manager)


NotificationSvc = Annotated[ReportNotificationService, Depends(get_notification_service)]


__all__ = [
    "ArchiveSvc",
    "AuditSvc",
    "CategoryRepo",
    "CurrentUserId",
    "CurrentUserToken",
    "DbSession",
    "DistributionSvc",
    "EventPublisherDep",
    "ExecutionRepo",
    "ExportRepo",
    "GenerationSvc",
    "JobSvc",
    "NotificationSvc",
    "ScheduleSvc",
    "StatisticsSvc",
    "TemplateSvc",
    "get_archive_service",
    "get_audit_service",
    "get_caller_token",
    "get_category_repository",
    "get_current_user_id",
    "get_db_session",
    "get_distribution_service",
    "get_event_publisher",
    "get_execution_repository",
    "get_export_repository",
    "get_generation_service",
    "get_http_client",
    "get_job_service",
    "get_notification_manager",
    "get_notification_service",
    "get_renderer",
    "get_schedule_service",
    "get_source_client",
    "get_statistics_service",
    "get_storage",
    "get_template_service",
]
