"""FastAPI dependency injection for the playbook service.

One factory function per business service, each building its own
repositories from the request-scoped database session -- routes depend
on services only, never repositories directly. Matches
``services/automation-service/app/api/deps.py``'s established shape.
The signing keypair is loaded once at process startup (``app/core
/factory.py``'s own lifespan) and handed to
:func:`get_signature_service` from application state, the same
"load once, never per-request" precedent every downstream AI-IOS
service's own JWT public key already established.
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

from app.notifications.playbook_notifications import PlaybookNotificationService
from app.repositories.playbook import PlaybookRepository
from app.repositories.playbook_approval import PlaybookApprovalRepository
from app.repositories.playbook_audit import PlaybookAuditRepository
from app.repositories.playbook_category import PlaybookCategoryRepository
from app.repositories.playbook_collection import PlaybookCollectionRepository
from app.repositories.playbook_dependency import PlaybookDependencyRepository
from app.repositories.playbook_label import PlaybookLabelRepository
from app.repositories.playbook_report import PlaybookReportRepository
from app.repositories.playbook_repository import PlaybookRepositoryFolderRepository
from app.repositories.playbook_review import PlaybookReviewRepository
from app.repositories.playbook_role import PlaybookRoleRepository
from app.repositories.playbook_script import PlaybookScriptRepository
from app.repositories.playbook_signature import PlaybookSignatureRepository
from app.repositories.playbook_statistics import PlaybookStatisticsRepository
from app.repositories.playbook_tag import PlaybookTagRepository
from app.repositories.playbook_template import PlaybookTemplateRepository
from app.repositories.playbook_variable import PlaybookVariableRepository
from app.repositories.playbook_version import PlaybookVersionRepository
from app.services.approval import PlaybookApprovalService
from app.services.audit import PlaybookAuditService
from app.services.category import PlaybookCategoryService
from app.services.collection import PlaybookCollectionService
from app.services.dependency import PlaybookDependencyService
from app.services.label import PlaybookLabelService
from app.services.playbook import PlaybookService
from app.services.report import PlaybookReportService
from app.services.repository_folder import PlaybookRepositoryFolderService
from app.services.review import PlaybookReviewService
from app.services.role import PlaybookRoleService
from app.services.script import PlaybookScriptService
from app.services.signature import PlaybookSignatureService
from app.services.statistics import PlaybookStatisticsService
from app.services.tag import PlaybookTagService
from app.services.template import PlaybookTemplateService
from app.services.variable import PlaybookVariableService
from app.services.version import PlaybookVersionService

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped database session, committing on success."""
    session_factory = request.app.state.db_session_factory
    async with session_scope(session_factory) as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db_session)]


def get_notification_manager(request: Request) -> NotificationManager:
    """The process-wide :class:`NotificationManager`."""
    return request.app.state.notification_manager  # type: ignore[no-any-return]


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


def get_notification_service(
    manager: Annotated[NotificationManager, Depends(get_notification_manager)],
) -> PlaybookNotificationService:
    """The current request's :class:`PlaybookNotificationService`."""
    return PlaybookNotificationService(manager)


def get_audit_service(session: DbSession) -> PlaybookAuditService:
    """The current request's :class:`PlaybookAuditService`."""
    return PlaybookAuditService(PlaybookAuditRepository(session))


AuditSvc = Annotated[PlaybookAuditService, Depends(get_audit_service)]


def get_version_service(request: Request, session: DbSession) -> PlaybookVersionService:
    """The current request's fully-wired :class:`PlaybookVersionService`."""
    return PlaybookVersionService(
        PlaybookVersionRepository(session),
        PlaybookRepository(session),
        publish_event=getattr(request.app.state, "publish_event", None),
    )


VersionSvc = Annotated[PlaybookVersionService, Depends(get_version_service)]


def get_playbook_service(
    request: Request, session: DbSession, versions: VersionSvc, audit: AuditSvc
) -> PlaybookService:
    """The current request's fully-wired :class:`PlaybookService`."""
    return PlaybookService(
        PlaybookRepository(session),
        versions,
        audit,
        publish_event=getattr(request.app.state, "publish_event", None),
    )


PlaybookSvc = Annotated[PlaybookService, Depends(get_playbook_service)]


def get_category_service(session: DbSession) -> PlaybookCategoryService:
    """The current request's :class:`PlaybookCategoryService`."""
    return PlaybookCategoryService(PlaybookCategoryRepository(session))


CategorySvc = Annotated[PlaybookCategoryService, Depends(get_category_service)]


def get_tag_service(session: DbSession) -> PlaybookTagService:
    """The current request's fully-wired :class:`PlaybookTagService`."""
    return PlaybookTagService(PlaybookTagRepository(session), PlaybookRepository(session))


TagSvc = Annotated[PlaybookTagService, Depends(get_tag_service)]


def get_label_service(session: DbSession) -> PlaybookLabelService:
    """The current request's fully-wired :class:`PlaybookLabelService`."""
    return PlaybookLabelService(PlaybookLabelRepository(session), PlaybookRepository(session))


LabelSvc = Annotated[PlaybookLabelService, Depends(get_label_service)]


def get_variable_service(session: DbSession) -> PlaybookVariableService:
    """The current request's fully-wired :class:`PlaybookVariableService`."""
    return PlaybookVariableService(PlaybookVariableRepository(session), PlaybookRepository(session))


VariableSvc = Annotated[PlaybookVariableService, Depends(get_variable_service)]


def get_dependency_service(session: DbSession) -> PlaybookDependencyService:
    """The current request's fully-wired :class:`PlaybookDependencyService`."""
    return PlaybookDependencyService(
        PlaybookDependencyRepository(session), PlaybookRepository(session)
    )


DependencySvc = Annotated[PlaybookDependencyService, Depends(get_dependency_service)]


def get_template_service(session: DbSession) -> PlaybookTemplateService:
    """The current request's :class:`PlaybookTemplateService`."""
    return PlaybookTemplateService(PlaybookTemplateRepository(session))


TemplateSvc = Annotated[PlaybookTemplateService, Depends(get_template_service)]


def get_script_service(session: DbSession) -> PlaybookScriptService:
    """The current request's fully-wired :class:`PlaybookScriptService`."""
    return PlaybookScriptService(PlaybookScriptRepository(session), PlaybookRepository(session))


ScriptSvc = Annotated[PlaybookScriptService, Depends(get_script_service)]


def get_role_service(session: DbSession) -> PlaybookRoleService:
    """The current request's fully-wired :class:`PlaybookRoleService`."""
    return PlaybookRoleService(PlaybookRoleRepository(session), PlaybookRepository(session))


RoleSvc = Annotated[PlaybookRoleService, Depends(get_role_service)]


def get_collection_service(session: DbSession) -> PlaybookCollectionService:
    """The current request's fully-wired :class:`PlaybookCollectionService`."""
    return PlaybookCollectionService(
        PlaybookCollectionRepository(session), PlaybookRepository(session)
    )


CollectionSvc = Annotated[PlaybookCollectionService, Depends(get_collection_service)]


def get_review_service(session: DbSession) -> PlaybookReviewService:
    """The current request's fully-wired :class:`PlaybookReviewService`."""
    return PlaybookReviewService(PlaybookReviewRepository(session), PlaybookRepository(session))


ReviewSvc = Annotated[PlaybookReviewService, Depends(get_review_service)]


def get_approval_service(request: Request, session: DbSession) -> PlaybookApprovalService:
    """The current request's fully-wired :class:`PlaybookApprovalService`."""
    return PlaybookApprovalService(
        PlaybookApprovalRepository(session),
        PlaybookRepository(session),
        publish_event=getattr(request.app.state, "publish_event", None),
    )


ApprovalSvc = Annotated[PlaybookApprovalService, Depends(get_approval_service)]


def get_signature_service(request: Request, session: DbSession) -> PlaybookSignatureService:
    """The current request's fully-wired :class:`PlaybookSignatureService`."""
    return PlaybookSignatureService(
        PlaybookSignatureRepository(session),
        PlaybookVersionRepository(session),
        publish_event=getattr(request.app.state, "publish_event", None),
    )


SignatureSvc = Annotated[PlaybookSignatureService, Depends(get_signature_service)]


def get_repository_folder_service(session: DbSession) -> PlaybookRepositoryFolderService:
    """The current request's :class:`PlaybookRepositoryFolderService`."""
    return PlaybookRepositoryFolderService(PlaybookRepositoryFolderRepository(session))


RepositoryFolderSvc = Annotated[
    PlaybookRepositoryFolderService, Depends(get_repository_folder_service)
]


def get_statistics_service(session: DbSession) -> PlaybookStatisticsService:
    """The current request's fully-wired :class:`PlaybookStatisticsService`."""
    return PlaybookStatisticsService(
        PlaybookStatisticsRepository(session),
        PlaybookRepository(session),
        PlaybookVersionRepository(session),
        PlaybookApprovalRepository(session),
    )


StatisticsSvc = Annotated[PlaybookStatisticsService, Depends(get_statistics_service)]


def get_report_service(
    session: DbSession,
    playbooks: PlaybookSvc,
    versions: VersionSvc,
    dependencies: DependencySvc,
    approvals: ApprovalSvc,
    statistics: StatisticsSvc,
) -> PlaybookReportService:
    """The current request's fully-wired :class:`PlaybookReportService`."""
    return PlaybookReportService(
        PlaybookReportRepository(session), playbooks, versions, dependencies, approvals, statistics
    )


ReportSvc = Annotated[PlaybookReportService, Depends(get_report_service)]


__all__ = [
    "ApprovalSvc",
    "AuditSvc",
    "CategorySvc",
    "CollectionSvc",
    "CurrentUserId",
    "DbSession",
    "DependencySvc",
    "LabelSvc",
    "PlaybookSvc",
    "ReportSvc",
    "RepositoryFolderSvc",
    "ReviewSvc",
    "RoleSvc",
    "ScriptSvc",
    "SignatureSvc",
    "StatisticsSvc",
    "TagSvc",
    "TemplateSvc",
    "VariableSvc",
    "VersionSvc",
    "get_approval_service",
    "get_audit_service",
    "get_category_service",
    "get_collection_service",
    "get_current_user_id",
    "get_db_session",
    "get_dependency_service",
    "get_label_service",
    "get_notification_manager",
    "get_notification_service",
    "get_playbook_service",
    "get_report_service",
    "get_repository_folder_service",
    "get_review_service",
    "get_role_service",
    "get_script_service",
    "get_signature_service",
    "get_statistics_service",
    "get_tag_service",
    "get_template_service",
    "get_variable_service",
    "get_version_service",
]
