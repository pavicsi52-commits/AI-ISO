"""Repositories for the RBAC service, one per model."""

from __future__ import annotations

from app.repositories.authorization_audit import AuthorizationAuditRepository
from app.repositories.authorization_policy import AuthorizationPolicyRepository
from app.repositories.organization_role import OrganizationRoleRepository
from app.repositories.permission import PermissionRepository
from app.repositories.permission_cache import PermissionCacheRepository
from app.repositories.permission_group import PermissionGroupRepository
from app.repositories.policy_assignment import PolicyAssignmentRepository
from app.repositories.policy_condition import PolicyConditionRepository
from app.repositories.project_role import ProjectRoleRepository
from app.repositories.resource_permission import ResourcePermissionRepository
from app.repositories.role import RoleRepository
from app.repositories.role_permission import RolePermissionRepository
from app.repositories.user_role import UserRoleRepository

__all__ = [
    "AuthorizationAuditRepository",
    "AuthorizationPolicyRepository",
    "OrganizationRoleRepository",
    "PermissionCacheRepository",
    "PermissionGroupRepository",
    "PermissionRepository",
    "PolicyAssignmentRepository",
    "PolicyConditionRepository",
    "ProjectRoleRepository",
    "ResourcePermissionRepository",
    "RolePermissionRepository",
    "RoleRepository",
    "UserRoleRepository",
]
