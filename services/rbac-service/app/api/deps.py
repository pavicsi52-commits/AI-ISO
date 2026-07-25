"""FastAPI dependency injection for the RBAC service.

One factory function per business service, each building its own
repositories from the request-scoped database session -- routes depend
on services only, never repositories directly, keeping the DB session
management entirely inside this module. Matches
``services/user-management-service/app/api/deps.py``'s established shape.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from shared_core.cache.manager import CacheManager
from shared_core.database.session import session_scope
from shared_core.exceptions.authentication import AuthenticationError
from shared_core.notifications.manager import NotificationManager
from shared_core.security.jwt import decode_token
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache.authorization_cache import AuthorizationCacheService
from app.config.settings import get_settings
from app.evaluators.authorization_evaluator import AuthorizationEvaluator
from app.notifications.rbac_notifications import RbacNotificationService
from app.repositories.authorization_audit import AuthorizationAuditRepository
from app.repositories.authorization_policy import AuthorizationPolicyRepository
from app.repositories.organization_role import OrganizationRoleRepository
from app.repositories.permission import PermissionRepository
from app.repositories.permission_group import PermissionGroupRepository
from app.repositories.policy_assignment import PolicyAssignmentRepository
from app.repositories.policy_condition import PolicyConditionRepository
from app.repositories.project_role import ProjectRoleRepository
from app.repositories.resource_permission import ResourcePermissionRepository
from app.repositories.role import RoleRepository
from app.repositories.role_permission import RolePermissionRepository
from app.repositories.user_role import UserRoleRepository
from app.services.permission import PermissionService
from app.services.permission_group import PermissionGroupService
from app.services.policy import PolicyService
from app.services.resource_authorization import ResourceAuthorizationService
from app.services.role import RoleService
from app.services.role_assignment import RoleAssignmentService
from app.services.role_permission import RolePermissionService

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped database session, committing on success.

    Per docs/018 "Transaction Session" -- see the identical rationale in
    ``services/authentication-service``/``services/user-management-service``'s
    own ``get_db_session``, whose live-smoke-tested fix this reuses
    directly (:func:`~shared_core.database.session.session_scope`).
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

    This service verifies identity tokens; it never issues them (see
    ``app/config/keys.py``'s docstring).

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
) -> RbacNotificationService:
    """The current request's :class:`RbacNotificationService`."""
    return RbacNotificationService(manager)


def get_authorization_cache_service(
    cache: Annotated[CacheManager, Depends(get_cache_manager)],
) -> AuthorizationCacheService:
    """The current request's :class:`AuthorizationCacheService`."""
    settings = get_settings()
    return AuthorizationCacheService(
        cache, ttl_seconds=settings.service.permission_cache_ttl_seconds
    )


AuthCacheSvc = Annotated[AuthorizationCacheService, Depends(get_authorization_cache_service)]


def get_role_service(request: Request, session: DbSession) -> RoleService:
    """The current request's fully-wired :class:`RoleService`."""
    return RoleService(
        RoleRepository(session),
        RolePermissionRepository(session),
        publish_event=getattr(request.app.state, "publish_event", None),
    )


RoleSvc = Annotated[RoleService, Depends(get_role_service)]


def get_permission_service(request: Request, session: DbSession) -> PermissionService:
    """The current request's fully-wired :class:`PermissionService`."""
    return PermissionService(
        PermissionRepository(session),
        publish_event=getattr(request.app.state, "publish_event", None),
    )


PermissionSvc = Annotated[PermissionService, Depends(get_permission_service)]


def get_permission_group_service(session: DbSession) -> PermissionGroupService:
    """The current request's :class:`PermissionGroupService`."""
    return PermissionGroupService(PermissionGroupRepository(session))


PermissionGroupSvc = Annotated[PermissionGroupService, Depends(get_permission_group_service)]


def get_role_permission_service(session: DbSession) -> RolePermissionService:
    """The current request's :class:`RolePermissionService`."""
    return RolePermissionService(
        RolePermissionRepository(session), RoleRepository(session), PermissionRepository(session)
    )


RolePermissionSvc = Annotated[RolePermissionService, Depends(get_role_permission_service)]


def get_role_assignment_service(request: Request, session: DbSession) -> RoleAssignmentService:
    """The current request's fully-wired :class:`RoleAssignmentService`."""
    return RoleAssignmentService(
        UserRoleRepository(session),
        OrganizationRoleRepository(session),
        ProjectRoleRepository(session),
        RoleRepository(session),
        publish_event=getattr(request.app.state, "publish_event", None),
    )


RoleAssignmentSvc = Annotated[RoleAssignmentService, Depends(get_role_assignment_service)]


def get_policy_service(request: Request, session: DbSession) -> PolicyService:
    """The current request's fully-wired :class:`PolicyService`."""
    return PolicyService(
        AuthorizationPolicyRepository(session),
        PolicyConditionRepository(session),
        PolicyAssignmentRepository(session),
        publish_event=getattr(request.app.state, "publish_event", None),
    )


PolicySvc = Annotated[PolicyService, Depends(get_policy_service)]


def get_resource_authorization_service(session: DbSession) -> ResourceAuthorizationService:
    """The current request's :class:`ResourceAuthorizationService`."""
    return ResourceAuthorizationService(ResourcePermissionRepository(session))


ResourceAuthSvc = Annotated[
    ResourceAuthorizationService, Depends(get_resource_authorization_service)
]


def get_authorization_evaluator(
    request: Request,
    session: DbSession,
    roles: RoleSvc,
    policies: PolicySvc,
    resources: ResourceAuthSvc,
) -> AuthorizationEvaluator:
    """The current request's fully-wired :class:`AuthorizationEvaluator`."""
    return AuthorizationEvaluator(
        UserRoleRepository(session),
        OrganizationRoleRepository(session),
        ProjectRoleRepository(session),
        PermissionRepository(session),
        PolicyAssignmentRepository(session),
        roles,
        policies,
        resources,
        AuthorizationAuditRepository(session),
        publish_event=getattr(request.app.state, "publish_event", None),
    )


EvaluatorSvc = Annotated[AuthorizationEvaluator, Depends(get_authorization_evaluator)]

__all__ = [
    "AuthCacheSvc",
    "CurrentUserId",
    "DbSession",
    "EvaluatorSvc",
    "PermissionGroupSvc",
    "PermissionSvc",
    "PolicySvc",
    "ResourceAuthSvc",
    "RoleAssignmentSvc",
    "RolePermissionSvc",
    "RoleSvc",
    "get_authorization_cache_service",
    "get_authorization_evaluator",
    "get_cache_manager",
    "get_current_user_id",
    "get_db_session",
    "get_notification_manager",
    "get_notification_service",
    "get_permission_group_service",
    "get_permission_service",
    "get_policy_service",
    "get_resource_authorization_service",
    "get_role_assignment_service",
    "get_role_permission_service",
    "get_role_service",
]
