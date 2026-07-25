"""FastAPI dependency injection for the organization service.

One factory function per business service, each building its own
repositories from the request-scoped database session -- routes depend
on services only, never repositories directly, keeping the DB session
management entirely inside this module. Matches
``services/rbac-service/app/api/deps.py``'s established shape.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Path, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from shared_core.cache.manager import CacheManager
from shared_core.database.session import session_scope
from shared_core.exceptions.authentication import AuthenticationError
from shared_core.exceptions.authorization import AuthorizationError
from shared_core.exceptions.not_found import NotFoundError
from shared_core.notifications.manager import NotificationManager
from shared_core.security.jwt import decode_token
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MemberRole
from app.notifications.organization_notifications import OrganizationNotificationService
from app.organizations.membership import role_at_least
from app.repositories.activity import OrganizationActivityRepository
from app.repositories.audit import OrganizationAuditRepository
from app.repositories.business_unit import BusinessUnitRepository
from app.repositories.department import DepartmentRepository
from app.repositories.invitation import OrganizationInvitationRepository
from app.repositories.member import OrganizationMemberRepository
from app.repositories.organization import OrganizationRepository
from app.repositories.organization_branding import OrganizationBrandingRepository
from app.repositories.organization_domain import OrganizationDomainRepository
from app.repositories.organization_license import OrganizationLicenseRepository
from app.repositories.organization_limits import OrganizationLimitsRepository
from app.repositories.organization_metadata import OrganizationMetadataRepository
from app.repositories.organization_preferences import OrganizationPreferencesRepository
from app.repositories.organization_quota import OrganizationQuotaRepository
from app.repositories.organization_settings import OrganizationSettingsRepository
from app.repositories.organization_subscription import OrganizationSubscriptionRepository
from app.repositories.statistics import OrganizationStatisticsRepository
from app.repositories.tag import OrganizationTagRepository
from app.repositories.team import TeamRepository
from app.services.activity import OrganizationActivityService
from app.services.audit import OrganizationAuditService
from app.services.branding import OrganizationBrandingService
from app.services.business_unit import BusinessUnitService
from app.services.department import DepartmentService
from app.services.domain import OrganizationDomainService
from app.services.invitation import InvitationService
from app.services.license import OrganizationLicenseService
from app.services.limits import OrganizationLimitsService
from app.services.member import OrganizationMemberService
from app.services.metadata import OrganizationMetadataService
from app.services.organization import OrganizationService
from app.services.preferences import OrganizationPreferencesService
from app.services.quota import OrganizationQuotaService
from app.services.settings import OrganizationSettingsService
from app.services.statistics import OrganizationStatisticsService
from app.services.subscription import OrganizationSubscriptionService
from app.services.tag import OrganizationTagService
from app.services.team import TeamService

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


def get_cache_manager(request: Request) -> CacheManager:
    """The process-wide :class:`CacheManager`."""
    return request.app.state.cache_manager  # type: ignore[no-any-return]


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
) -> OrganizationNotificationService:
    """The current request's :class:`OrganizationNotificationService`."""
    return OrganizationNotificationService(manager)


def get_activity_service(session: DbSession) -> OrganizationActivityService:
    """The current request's :class:`OrganizationActivityService`."""
    return OrganizationActivityService(OrganizationActivityRepository(session))


ActivitySvc = Annotated[OrganizationActivityService, Depends(get_activity_service)]


def get_audit_service(session: DbSession) -> OrganizationAuditService:
    """The current request's :class:`OrganizationAuditService`."""
    return OrganizationAuditService(OrganizationAuditRepository(session))


AuditSvc = Annotated[OrganizationAuditService, Depends(get_audit_service)]


def get_member_service(session: DbSession, activity: ActivitySvc) -> OrganizationMemberService:
    """The current request's :class:`OrganizationMemberService`."""
    return OrganizationMemberService(OrganizationMemberRepository(session), activity)


MemberSvc = Annotated[OrganizationMemberService, Depends(get_member_service)]


async def require_role_in_org(
    organization_id: UUID, caller_id: UUID, members: OrganizationMemberService, minimum: MemberRole
) -> None:
    """Require *caller_id* hold at least *minimum* role in *organization_id*
    ("Validate organization ownership", "Prevent cross-tenant access").

    Raises:
        AuthorizationError: If the caller is not a member, or holds too low a role.
    """
    try:
        member = await members.get(organization_id, caller_id)
    except NotFoundError as exc:
        raise AuthorizationError("You are not a member of this organization.") from exc
    if not role_at_least(member.role, minimum):
        raise AuthorizationError(f"This action requires at least the {minimum.value!r} role.")


async def require_admin(
    organization_id: Annotated[UUID, Path()], caller_id: CurrentUserId, members: MemberSvc
) -> None:
    """A dependency requiring the caller hold at least the admin role in the
    organization named by the ``organization_id`` path parameter.
    """
    await require_role_in_org(organization_id, caller_id, members, MemberRole.ADMIN)


async def require_member(
    organization_id: Annotated[UUID, Path()], caller_id: CurrentUserId, members: MemberSvc
) -> None:
    """A dependency requiring the caller hold at least the member role in the
    organization named by the ``organization_id`` path parameter.

    Gates read access to organization-scoped sub-resources (settings,
    branding, departments, teams, licenses, quotas, analytics) per
    docs/033's "SECURITY" section ("Strict tenant isolation.", "Prevent
    cross-tenant access."). The top-level ``/organizations`` directory
    endpoints (list/get) deliberately do *not* use this guard -- they
    expose only an organization's own basic public identity (name, slug,
    domain, status) to any authenticated platform user, the same
    directory-level visibility every organization's own listing already
    grants.
    """
    await require_role_in_org(organization_id, caller_id, members, MemberRole.MEMBER)


def get_organization_service(
    request: Request, session: DbSession, activity: ActivitySvc
) -> OrganizationService:
    """The current request's fully-wired :class:`OrganizationService`."""
    return OrganizationService(
        OrganizationRepository(session),
        OrganizationSettingsRepository(session),
        OrganizationPreferencesRepository(session),
        OrganizationBrandingRepository(session),
        OrganizationSubscriptionRepository(session),
        OrganizationLimitsRepository(session),
        OrganizationQuotaRepository(session),
        activity,
        publish_event=getattr(request.app.state, "publish_event", None),
    )


OrgSvc = Annotated[OrganizationService, Depends(get_organization_service)]


def get_settings_service(session: DbSession, activity: ActivitySvc) -> OrganizationSettingsService:
    """The current request's :class:`OrganizationSettingsService`."""
    return OrganizationSettingsService(OrganizationSettingsRepository(session), activity)


SettingsSvc = Annotated[OrganizationSettingsService, Depends(get_settings_service)]


def get_branding_service(session: DbSession, activity: ActivitySvc) -> OrganizationBrandingService:
    """The current request's :class:`OrganizationBrandingService`."""
    return OrganizationBrandingService(OrganizationBrandingRepository(session), activity)


BrandingSvc = Annotated[OrganizationBrandingService, Depends(get_branding_service)]


def get_department_service(
    request: Request, session: DbSession, activity: ActivitySvc
) -> DepartmentService:
    """The current request's fully-wired :class:`DepartmentService`."""
    return DepartmentService(
        DepartmentRepository(session),
        activity,
        publish_event=getattr(request.app.state, "publish_event", None),
    )


DepartmentSvc = Annotated[DepartmentService, Depends(get_department_service)]


def get_business_unit_service(session: DbSession) -> BusinessUnitService:
    """The current request's :class:`BusinessUnitService`."""
    return BusinessUnitService(BusinessUnitRepository(session))


BusinessUnitSvc = Annotated[BusinessUnitService, Depends(get_business_unit_service)]


def get_team_service(request: Request, session: DbSession, activity: ActivitySvc) -> TeamService:
    """The current request's fully-wired :class:`TeamService`."""
    return TeamService(
        TeamRepository(session),
        activity,
        publish_event=getattr(request.app.state, "publish_event", None),
    )


TeamSvc = Annotated[TeamService, Depends(get_team_service)]


def get_license_service(session: DbSession, activity: ActivitySvc) -> OrganizationLicenseService:
    """The current request's :class:`OrganizationLicenseService`."""
    return OrganizationLicenseService(OrganizationLicenseRepository(session), activity)


LicenseSvc = Annotated[OrganizationLicenseService, Depends(get_license_service)]


def get_quota_service(session: DbSession, activity: ActivitySvc) -> OrganizationQuotaService:
    """The current request's :class:`OrganizationQuotaService`."""
    return OrganizationQuotaService(
        OrganizationQuotaRepository(session), OrganizationMemberRepository(session), activity
    )


QuotaSvc = Annotated[OrganizationQuotaService, Depends(get_quota_service)]


def get_limits_service(session: DbSession) -> OrganizationLimitsService:
    """The current request's :class:`OrganizationLimitsService`."""
    return OrganizationLimitsService(OrganizationLimitsRepository(session))


LimitsSvc = Annotated[OrganizationLimitsService, Depends(get_limits_service)]


def get_subscription_service(
    session: DbSession, activity: ActivitySvc
) -> OrganizationSubscriptionService:
    """The current request's :class:`OrganizationSubscriptionService`."""
    return OrganizationSubscriptionService(OrganizationSubscriptionRepository(session), activity)


SubscriptionSvc = Annotated[OrganizationSubscriptionService, Depends(get_subscription_service)]


def get_invitation_service(
    request: Request,
    session: DbSession,
    activity: ActivitySvc,
    notifications: Annotated[OrganizationNotificationService, Depends(get_notification_service)],
    quotas: Annotated[OrganizationQuotaService, Depends(get_quota_service)],
) -> InvitationService:
    """The current request's fully-wired :class:`InvitationService`."""
    return InvitationService(
        OrganizationInvitationRepository(session),
        OrganizationMemberRepository(session),
        activity,
        notifications,
        quotas,
        publish_event=getattr(request.app.state, "publish_event", None),
    )


InvitationSvc = Annotated[InvitationService, Depends(get_invitation_service)]


def get_statistics_service(session: DbSession) -> OrganizationStatisticsService:
    """The current request's :class:`OrganizationStatisticsService`."""
    return OrganizationStatisticsService(
        OrganizationStatisticsRepository(session),
        OrganizationMemberRepository(session),
        OrganizationLicenseRepository(session),
    )


StatisticsSvc = Annotated[OrganizationStatisticsService, Depends(get_statistics_service)]


def get_preferences_service(session: DbSession) -> OrganizationPreferencesService:
    """The current request's :class:`OrganizationPreferencesService`."""
    return OrganizationPreferencesService(OrganizationPreferencesRepository(session))


PreferencesSvc = Annotated[OrganizationPreferencesService, Depends(get_preferences_service)]


def get_metadata_service(session: DbSession) -> OrganizationMetadataService:
    """The current request's :class:`OrganizationMetadataService`."""
    return OrganizationMetadataService(OrganizationMetadataRepository(session))


MetadataSvc = Annotated[OrganizationMetadataService, Depends(get_metadata_service)]


def get_tag_service(session: DbSession) -> OrganizationTagService:
    """The current request's :class:`OrganizationTagService`."""
    return OrganizationTagService(OrganizationTagRepository(session))


TagSvc = Annotated[OrganizationTagService, Depends(get_tag_service)]


def get_domain_service(session: DbSession) -> OrganizationDomainService:
    """The current request's :class:`OrganizationDomainService`."""
    return OrganizationDomainService(OrganizationDomainRepository(session))


DomainSvc = Annotated[OrganizationDomainService, Depends(get_domain_service)]

__all__ = [
    "ActivitySvc",
    "AuditSvc",
    "BrandingSvc",
    "BusinessUnitSvc",
    "CurrentUserId",
    "DbSession",
    "DepartmentSvc",
    "DomainSvc",
    "InvitationSvc",
    "LicenseSvc",
    "LimitsSvc",
    "MemberSvc",
    "MetadataSvc",
    "OrgSvc",
    "PreferencesSvc",
    "QuotaSvc",
    "SettingsSvc",
    "StatisticsSvc",
    "SubscriptionSvc",
    "TagSvc",
    "TeamSvc",
    "get_activity_service",
    "get_audit_service",
    "get_branding_service",
    "get_business_unit_service",
    "get_cache_manager",
    "get_current_user_id",
    "get_db_session",
    "get_department_service",
    "get_domain_service",
    "get_invitation_service",
    "get_license_service",
    "get_limits_service",
    "get_member_service",
    "get_metadata_service",
    "get_notification_manager",
    "get_notification_service",
    "get_organization_service",
    "get_preferences_service",
    "get_quota_service",
    "get_settings_service",
    "get_statistics_service",
    "get_subscription_service",
    "get_tag_service",
    "get_team_service",
    "require_admin",
    "require_member",
    "require_role_in_org",
]
