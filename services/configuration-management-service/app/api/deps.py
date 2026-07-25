"""FastAPI dependency injection for the configuration management service.

One factory function per business service, each building its own
repositories from the request-scoped database session -- routes depend
on services only, never repositories directly. Matches
``services/asset-management-service/app/api/deps.py``'s established
shape, with the addition of :func:`get_gitops_service` (this service's
own cross-service secret resolution, mirroring that service's
``get_caller_token``/``get_inventory_client`` precedent) and no Neo4j
dependency (docs/039 names no graph concept for this service).
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

from app.gitops.credentials import GitCredentialResolver
from app.notifications.configuration_notifications import ConfigurationNotificationService
from app.repositories.configuration_ansible_inventory import (
    ConfigurationAnsibleInventoryRepository,
)
from app.repositories.configuration_approval import ConfigurationApprovalRepository
from app.repositories.configuration_assignment import ConfigurationAssignmentRepository
from app.repositories.configuration_audit import ConfigurationAuditRepository
from app.repositories.configuration_backup import ConfigurationBackupRepository
from app.repositories.configuration_baseline import ConfigurationBaselineRepository
from app.repositories.configuration_change_set import ConfigurationChangeSetRepository
from app.repositories.configuration_compliance import ConfigurationComplianceRepository
from app.repositories.configuration_drift import ConfigurationDriftRepository
from app.repositories.configuration_environment import ConfigurationEnvironmentRepository
from app.repositories.configuration_git_repository import ConfigurationGitRepositoryRepository
from app.repositories.configuration_kubernetes_manifest import (
    ConfigurationKubernetesManifestRepository,
)
from app.repositories.configuration_policy import ConfigurationPolicyRepository
from app.repositories.configuration_profile import ConfigurationProfileRepository
from app.repositories.configuration_report import ConfigurationReportRepository
from app.repositories.configuration_restore_job import ConfigurationRestoreJobRepository
from app.repositories.configuration_rollback import ConfigurationRollbackRepository
from app.repositories.configuration_statistics import ConfigurationStatisticsRepository
from app.repositories.configuration_template import ConfigurationTemplateRepository
from app.repositories.configuration_tosca_template import ConfigurationToscaTemplateRepository
from app.repositories.configuration_variable import ConfigurationVariableRepository
from app.repositories.configuration_version import ConfigurationVersionRepository
from app.services.ansible import ConfigurationAnsibleService
from app.services.approval import ConfigurationApprovalService
from app.services.assignment import ConfigurationAssignmentService
from app.services.audit import ConfigurationAuditService
from app.services.backup import ConfigurationBackupService
from app.services.baseline import ConfigurationBaselineService
from app.services.change_set import ConfigurationChangeSetService
from app.services.compliance import ConfigurationComplianceService
from app.services.drift import ConfigurationDriftService
from app.services.environment import ConfigurationEnvironmentService
from app.services.gitops import ConfigurationGitOpsService
from app.services.kubernetes import ConfigurationKubernetesService
from app.services.policy import ConfigurationPolicyService
from app.services.profile import ConfigurationProfileService
from app.services.report import ConfigurationReportService
from app.services.restore import ConfigurationRestoreService
from app.services.rollback import ConfigurationRollbackService
from app.services.statistics import ConfigurationStatisticsService
from app.services.template import ConfigurationTemplateService
from app.services.tosca import ConfigurationToscaService
from app.services.variable import ConfigurationVariableService
from app.services.version import ConfigurationVersionService

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped database session, committing on success."""
    session_factory = request.app.state.db_session_factory
    async with session_scope(session_factory) as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db_session)]


def get_http_client(request: Request) -> httpx.AsyncClient:
    """The process-wide :class:`httpx.AsyncClient` shared by every
    cross-service call this service makes (Git providers, Secrets
    Management Service).
    """
    return request.app.state.http_client  # type: ignore[no-any-return]


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


async def get_caller_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
) -> str:
    """The raw Bearer token string, forwarded to the Secrets Management
    Service on this caller's behalf -- see ``app/gitops/credentials.py``.

    Raises:
        AuthenticationError: If no valid Bearer token is presented.
    """
    if credentials is None:
        raise AuthenticationError("Authentication required.")
    return credentials.credentials


CurrentUserToken = Annotated[str, Depends(get_caller_token)]


def get_notification_service(
    manager: Annotated[NotificationManager, Depends(get_notification_manager)],
) -> ConfigurationNotificationService:
    """The current request's :class:`ConfigurationNotificationService`."""
    return ConfigurationNotificationService(manager)


def get_credential_resolver(
    client: Annotated[httpx.AsyncClient, Depends(get_http_client)], request: Request
) -> GitCredentialResolver:
    """The current request's :class:`GitCredentialResolver`."""
    settings = request.app.state.service_settings
    return GitCredentialResolver(client, base_url=settings.secrets_service_base_url)


def get_audit_service(session: DbSession) -> ConfigurationAuditService:
    """The current request's :class:`ConfigurationAuditService`."""
    return ConfigurationAuditService(ConfigurationAuditRepository(session))


AuditSvc = Annotated[ConfigurationAuditService, Depends(get_audit_service)]


def get_version_service(session: DbSession) -> ConfigurationVersionService:
    """The current request's :class:`ConfigurationVersionService`."""
    return ConfigurationVersionService(ConfigurationVersionRepository(session))


VersionSvc = Annotated[ConfigurationVersionService, Depends(get_version_service)]


def get_profile_service(
    request: Request, session: DbSession, versions: VersionSvc, audit: AuditSvc
) -> ConfigurationProfileService:
    """The current request's fully-wired :class:`ConfigurationProfileService`."""
    return ConfigurationProfileService(
        ConfigurationProfileRepository(session),
        versions,
        audit,
        publish_event=getattr(request.app.state, "publish_event", None),
    )


ProfileSvc = Annotated[ConfigurationProfileService, Depends(get_profile_service)]


def get_template_service(session: DbSession) -> ConfigurationTemplateService:
    """The current request's :class:`ConfigurationTemplateService`."""
    return ConfigurationTemplateService(ConfigurationTemplateRepository(session))


TemplateSvc = Annotated[ConfigurationTemplateService, Depends(get_template_service)]


def get_baseline_service(session: DbSession) -> ConfigurationBaselineService:
    """The current request's :class:`ConfigurationBaselineService`."""
    return ConfigurationBaselineService(ConfigurationBaselineRepository(session))


BaselineSvc = Annotated[ConfigurationBaselineService, Depends(get_baseline_service)]


def get_variable_service(session: DbSession) -> ConfigurationVariableService:
    """The current request's :class:`ConfigurationVariableService`."""
    return ConfigurationVariableService(ConfigurationVariableRepository(session))


VariableSvc = Annotated[ConfigurationVariableService, Depends(get_variable_service)]


def get_environment_service(session: DbSession) -> ConfigurationEnvironmentService:
    """The current request's :class:`ConfigurationEnvironmentService`."""
    return ConfigurationEnvironmentService(ConfigurationEnvironmentRepository(session))


EnvironmentSvc = Annotated[ConfigurationEnvironmentService, Depends(get_environment_service)]


def get_assignment_service(request: Request, session: DbSession) -> ConfigurationAssignmentService:
    """The current request's fully-wired :class:`ConfigurationAssignmentService`."""
    return ConfigurationAssignmentService(
        ConfigurationAssignmentRepository(session),
        ConfigurationProfileRepository(session),
        publish_event=getattr(request.app.state, "publish_event", None),
    )


AssignmentSvc = Annotated[ConfigurationAssignmentService, Depends(get_assignment_service)]


def get_drift_service(request: Request, session: DbSession) -> ConfigurationDriftService:
    """The current request's fully-wired :class:`ConfigurationDriftService`."""
    return ConfigurationDriftService(
        ConfigurationDriftRepository(session),
        publish_event=getattr(request.app.state, "publish_event", None),
    )


DriftSvc = Annotated[ConfigurationDriftService, Depends(get_drift_service)]


def get_compliance_service(request: Request, session: DbSession) -> ConfigurationComplianceService:
    """The current request's fully-wired :class:`ConfigurationComplianceService`."""
    return ConfigurationComplianceService(
        ConfigurationComplianceRepository(session),
        ConfigurationProfileRepository(session),
        publish_event=getattr(request.app.state, "publish_event", None),
    )


ComplianceSvc = Annotated[ConfigurationComplianceService, Depends(get_compliance_service)]


def get_backup_service(request: Request, session: DbSession) -> ConfigurationBackupService:
    """The current request's fully-wired :class:`ConfigurationBackupService`."""
    return ConfigurationBackupService(
        ConfigurationBackupRepository(session),
        ConfigurationProfileRepository(session),
        publish_event=getattr(request.app.state, "publish_event", None),
    )


BackupSvc = Annotated[ConfigurationBackupService, Depends(get_backup_service)]


def get_restore_service(
    request: Request, session: DbSession, versions: VersionSvc
) -> ConfigurationRestoreService:
    """The current request's fully-wired :class:`ConfigurationRestoreService`."""
    return ConfigurationRestoreService(
        ConfigurationRestoreJobRepository(session),
        ConfigurationBackupRepository(session),
        ConfigurationProfileRepository(session),
        versions,
        publish_event=getattr(request.app.state, "publish_event", None),
    )


RestoreSvc = Annotated[ConfigurationRestoreService, Depends(get_restore_service)]


def get_rollback_service(
    request: Request, session: DbSession, versions: VersionSvc
) -> ConfigurationRollbackService:
    """The current request's fully-wired :class:`ConfigurationRollbackService`."""
    return ConfigurationRollbackService(
        ConfigurationRollbackRepository(session),
        versions,
        ConfigurationProfileRepository(session),
        publish_event=getattr(request.app.state, "publish_event", None),
    )


RollbackSvc = Annotated[ConfigurationRollbackService, Depends(get_rollback_service)]


def get_change_set_service(
    session: DbSession, versions: VersionSvc
) -> ConfigurationChangeSetService:
    """The current request's fully-wired :class:`ConfigurationChangeSetService`."""
    return ConfigurationChangeSetService(
        ConfigurationChangeSetRepository(session), ConfigurationProfileRepository(session), versions
    )


ChangeSetSvc = Annotated[ConfigurationChangeSetService, Depends(get_change_set_service)]


def get_gitops_service(
    session: DbSession,
    client: Annotated[httpx.AsyncClient, Depends(get_http_client)],
    credentials: Annotated[GitCredentialResolver, Depends(get_credential_resolver)],
) -> ConfigurationGitOpsService:
    """The current request's fully-wired :class:`ConfigurationGitOpsService`."""
    return ConfigurationGitOpsService(
        ConfigurationGitRepositoryRepository(session), client, credentials
    )


GitOpsSvc = Annotated[ConfigurationGitOpsService, Depends(get_gitops_service)]


def get_tosca_service(session: DbSession) -> ConfigurationToscaService:
    """The current request's :class:`ConfigurationToscaService`."""
    return ConfigurationToscaService(ConfigurationToscaTemplateRepository(session))


ToscaSvc = Annotated[ConfigurationToscaService, Depends(get_tosca_service)]


def get_ansible_service(session: DbSession) -> ConfigurationAnsibleService:
    """The current request's :class:`ConfigurationAnsibleService`."""
    return ConfigurationAnsibleService(ConfigurationAnsibleInventoryRepository(session))


AnsibleSvc = Annotated[ConfigurationAnsibleService, Depends(get_ansible_service)]


def get_kubernetes_service(session: DbSession) -> ConfigurationKubernetesService:
    """The current request's :class:`ConfigurationKubernetesService`."""
    return ConfigurationKubernetesService(ConfigurationKubernetesManifestRepository(session))


KubernetesSvc = Annotated[ConfigurationKubernetesService, Depends(get_kubernetes_service)]


def get_policy_service(session: DbSession) -> ConfigurationPolicyService:
    """The current request's :class:`ConfigurationPolicyService`."""
    return ConfigurationPolicyService(ConfigurationPolicyRepository(session))


PolicySvc = Annotated[ConfigurationPolicyService, Depends(get_policy_service)]


def get_approval_service(request: Request, session: DbSession) -> ConfigurationApprovalService:
    """The current request's fully-wired :class:`ConfigurationApprovalService`."""
    return ConfigurationApprovalService(
        ConfigurationApprovalRepository(session),
        publish_event=getattr(request.app.state, "publish_event", None),
    )


ApprovalSvc = Annotated[ConfigurationApprovalService, Depends(get_approval_service)]


def get_statistics_service(session: DbSession) -> ConfigurationStatisticsService:
    """The current request's :class:`ConfigurationStatisticsService`."""
    return ConfigurationStatisticsService(
        ConfigurationStatisticsRepository(session),
        ConfigurationProfileRepository(session),
        ConfigurationVersionRepository(session),
        ConfigurationDriftRepository(session),
        ConfigurationComplianceRepository(session),
        ConfigurationRollbackRepository(session),
        ConfigurationChangeSetRepository(session),
    )


StatisticsSvc = Annotated[ConfigurationStatisticsService, Depends(get_statistics_service)]


def get_report_service(
    session: DbSession,
    profiles: ProfileSvc,
    compliance: ComplianceSvc,
    drift: DriftSvc,
    baselines: BaselineSvc,
    versions: VersionSvc,
    approvals: ApprovalSvc,
    statistics: StatisticsSvc,
) -> ConfigurationReportService:
    """The current request's fully-wired :class:`ConfigurationReportService`."""
    return ConfigurationReportService(
        ConfigurationReportRepository(session),
        profiles,
        compliance,
        drift,
        baselines,
        versions,
        approvals,
        statistics,
    )


ReportSvc = Annotated[ConfigurationReportService, Depends(get_report_service)]

__all__ = [
    "AnsibleSvc",
    "ApprovalSvc",
    "AssignmentSvc",
    "AuditSvc",
    "BackupSvc",
    "BaselineSvc",
    "ChangeSetSvc",
    "ComplianceSvc",
    "CurrentUserId",
    "CurrentUserToken",
    "DbSession",
    "DriftSvc",
    "EnvironmentSvc",
    "GitOpsSvc",
    "KubernetesSvc",
    "PolicySvc",
    "ProfileSvc",
    "ReportSvc",
    "RestoreSvc",
    "RollbackSvc",
    "StatisticsSvc",
    "TemplateSvc",
    "ToscaSvc",
    "VariableSvc",
    "VersionSvc",
    "get_ansible_service",
    "get_approval_service",
    "get_assignment_service",
    "get_audit_service",
    "get_backup_service",
    "get_baseline_service",
    "get_caller_token",
    "get_change_set_service",
    "get_compliance_service",
    "get_credential_resolver",
    "get_current_user_id",
    "get_db_session",
    "get_drift_service",
    "get_environment_service",
    "get_gitops_service",
    "get_http_client",
    "get_kubernetes_service",
    "get_notification_manager",
    "get_notification_service",
    "get_policy_service",
    "get_profile_service",
    "get_report_service",
    "get_restore_service",
    "get_rollback_service",
    "get_statistics_service",
    "get_template_service",
    "get_tosca_service",
    "get_variable_service",
    "get_version_service",
]
