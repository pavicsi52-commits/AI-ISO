"""SQLAlchemy models for the RBAC service.

Every model must be imported here so it registers with
:data:`shared_core.database.base.Base.metadata` -- both Alembic
autogenerate and any create_all() call rely on every table being
known before they run.
"""

from __future__ import annotations

from app.models.authorization_audit import AuthorizationAuditEntry
from app.models.authorization_policy import AuthorizationPolicy
from app.models.organization_role import OrganizationRole
from app.models.permission import Permission
from app.models.permission_cache import PermissionCacheEntry
from app.models.permission_group import PermissionGroup
from app.models.policy_assignment import PolicyAssignment
from app.models.policy_condition import PolicyCondition
from app.models.project_role import ProjectRole
from app.models.resource_permission import ResourcePermission
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.models.user_role import UserRole

__all__ = [
    "AuthorizationAuditEntry",
    "AuthorizationPolicy",
    "OrganizationRole",
    "Permission",
    "PermissionCacheEntry",
    "PermissionGroup",
    "PolicyAssignment",
    "PolicyCondition",
    "ProjectRole",
    "ResourcePermission",
    "Role",
    "RolePermission",
    "UserRole",
]
