"""FastAPI dependency injection for the plugin marketplace service.

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
from shared_core.security.jwt import decode_token
from shared_core.storage.wrapper import StorageWrapper
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.dependency import PluginDependencyRepository
from app.repositories.governance import (
    PluginAuditRepository,
    PluginReportRepository,
    PluginStatisticRepository,
)
from app.repositories.health import PluginHealthRepository
from app.repositories.installation import PluginInstallationRepository
from app.repositories.manifest import PluginManifestRepository
from app.repositories.marketplace import PluginMarketplaceRepository
from app.repositories.package import PluginPackageRepository
from app.repositories.permission import PluginPermissionRepository
from app.repositories.plugin import PluginRepository, PluginVersionRepository
from app.repositories.publisher import PluginPublisherRepository
from app.repositories.review import PluginRatingRepository, PluginReviewRepository
from app.repositories.upgrade import PluginRollbackRepository, PluginUpgradeRepository
from app.services.dependency import PluginDependencyService
from app.services.health import PluginHealthService
from app.services.installation import PluginInstallationService
from app.services.marketplace import PluginMarketplaceService
from app.services.package import PluginPackageService
from app.services.permission import PluginPermissionService
from app.services.plugin import PluginService
from app.services.publisher import PluginPublisherService
from app.services.reporting import AuditService, ReportService, StatisticsService
from app.services.review import PluginReviewService
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


def get_plugin_service(session: DbSession, publish_event: EventPublisherDep) -> PluginService:
    """The current request's plugin lifecycle service."""
    return PluginService(
        PluginRepository(session),
        PluginVersionRepository(session),
        PluginManifestRepository(session),
        publish_event=publish_event,
    )


PluginSvc = Annotated[PluginService, Depends(get_plugin_service)]


def get_package_service(session: DbSession, request: Request) -> PluginPackageService:
    """The current request's packaging/signing service."""
    settings = request.app.state.service_settings
    storage = StorageWrapper(request.app.state.minio_client)
    return PluginPackageService(
        PluginPackageRepository(session), storage, bucket=settings.package_storage_bucket
    )


PackageSvc = Annotated[PluginPackageService, Depends(get_package_service)]


def get_dependency_service(session: DbSession) -> PluginDependencyService:
    """The current request's dependency-graph service."""
    return PluginDependencyService(PluginDependencyRepository(session))


DependencySvc = Annotated[PluginDependencyService, Depends(get_dependency_service)]


def get_permission_service(session: DbSession) -> PluginPermissionService:
    """The current request's capability-grant service."""
    return PluginPermissionService(PluginPermissionRepository(session))


PermissionSvc = Annotated[PluginPermissionService, Depends(get_permission_service)]


def get_installation_service(
    session: DbSession, publish_event: EventPublisherDep
) -> PluginInstallationService:
    """The current request's installation lifecycle service."""
    return PluginInstallationService(
        PluginInstallationRepository(session),
        PluginRepository(session),
        PluginVersionRepository(session),
        PluginDependencyRepository(session),
        PluginUpgradeRepository(session),
        PluginRollbackRepository(session),
        publish_event=publish_event,
    )


InstallationSvc = Annotated[PluginInstallationService, Depends(get_installation_service)]


def get_health_service(session: DbSession, request: Request) -> PluginHealthService:
    """The current request's health-probing service."""
    settings = request.app.state.service_settings
    return PluginHealthService(
        PluginHealthRepository(session),
        timeout_seconds=settings.health_check_timeout_seconds,
        failure_threshold=settings.health_failure_threshold,
    )


HealthSvc = Annotated[PluginHealthService, Depends(get_health_service)]


def get_review_service(session: DbSession) -> PluginReviewService:
    """The current request's review/rating service."""
    return PluginReviewService(PluginReviewRepository(session), PluginRatingRepository(session))


ReviewSvc = Annotated[PluginReviewService, Depends(get_review_service)]


def get_publisher_service(session: DbSession) -> PluginPublisherService:
    """The current request's publisher-profile service."""
    return PluginPublisherService(PluginPublisherRepository(session))


PublisherSvc = Annotated[PluginPublisherService, Depends(get_publisher_service)]


def get_marketplace_service(
    session: DbSession, publish_event: EventPublisherDep
) -> PluginMarketplaceService:
    """The current request's marketplace-listing service."""
    return PluginMarketplaceService(
        PluginMarketplaceRepository(session), publish_event=publish_event
    )


MarketplaceSvc = Annotated[PluginMarketplaceService, Depends(get_marketplace_service)]


def get_statistics_service(session: DbSession) -> StatisticsService:
    """The current request's statistics service."""
    return StatisticsService(
        PluginStatisticRepository(session),
        PluginRepository(session),
        PluginInstallationRepository(session),
        PluginReviewRepository(session),
    )


StatisticsSvc = Annotated[StatisticsService, Depends(get_statistics_service)]


def get_report_service(session: DbSession, request: Request) -> ReportService:
    """The current request's report service."""
    settings = request.app.state.service_settings
    return ReportService(
        PluginReportRepository(session),
        PluginRepository(session),
        PluginInstallationRepository(session),
        PluginPublisherRepository(session),
        PluginAuditRepository(session),
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
        PluginAuditRepository(session), session_factory=request.app.state.db_session_factory
    )


AuditSvc = Annotated[AuditService, Depends(get_audit_service)]
