"""Enumerations for the RBAC service's persisted domain.

Per docs/032 "ROLE TYPES"/"PERMISSION ACTIONS"/"RESOURCE TYPES"/
"PERMISSION GROUPS"/"POLICY ENGINE". These are this service's own
*dynamic, persisted* catalog -- distinct from
:mod:`shared_core.enums.role`/:mod:`shared_core.enums.permission`,
which are a small, fixed, code-level set used for shared-core's
in-memory RBAC primitives. A platform administrator can define
arbitrary custom roles and permissions at runtime here; the fixed
shared-core enums couldn't represent that even if reused directly.
"""

from __future__ import annotations

from enum import StrEnum


class RoleType(StrEnum):
    """Per docs/032 "ROLE TYPES" (7 values, verbatim)."""

    SYSTEM = "system"
    ORGANIZATION = "organization"
    PROJECT = "project"
    CUSTOM = "custom"
    TEMPORARY = "temporary"
    READ_ONLY = "read_only"
    SERVICE = "service"


class RoleStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"


class PermissionAction(StrEnum):
    """Per docs/032 "PERMISSION ACTIONS" (16 values, verbatim)."""

    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    EXECUTE = "execute"
    APPROVE = "approve"
    IMPORT = "import"
    EXPORT = "export"
    ASSIGN = "assign"
    MANAGE = "manage"
    CONFIGURE = "configure"
    AUDIT = "audit"
    MONITOR = "monitor"
    SCHEDULE = "schedule"
    DEPLOY = "deploy"
    ROLLBACK = "rollback"


class ResourceType(StrEnum):
    """Per docs/032 "RESOURCE TYPES" (20 values, verbatim)."""

    USERS = "users"
    ORGANIZATIONS = "organizations"
    PROJECTS = "projects"
    ASSETS = "assets"
    INVENTORY = "inventory"
    AUTOMATION = "automation"
    WORKFLOWS = "workflows"
    VALIDATION = "validation"
    MONITORING = "monitoring"
    NOTIFICATIONS = "notifications"
    REPORTS = "reports"
    DASHBOARDS = "dashboards"
    PLUGINS = "plugins"
    CONNECTORS = "connectors"
    SETTINGS = "settings"
    SECRETS = "secrets"
    AI = "ai"
    STORAGE = "storage"
    SCHEDULER = "scheduler"
    API_KEYS = "api_keys"


class PermissionStatus(StrEnum):
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    INACTIVE = "inactive"


class PermissionGroupCategory(StrEnum):
    """Per docs/032 "PERMISSION GROUPS" (9 values, verbatim)."""

    INFRASTRUCTURE = "infrastructure"
    AUTOMATION = "automation"
    VALIDATION = "validation"
    MONITORING = "monitoring"
    SECURITY = "security"
    ADMINISTRATION = "administration"
    AI = "ai"
    REPORTING = "reporting"
    CUSTOM = "custom"


class AssignmentStatus(StrEnum):
    """Status of a role assignment (``user_roles``/``organization_roles``/``project_roles``)."""

    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"


class SubjectType(StrEnum):
    """Who a resource grant or policy assignment applies to."""

    USER = "user"
    ROLE = "role"
    ORGANIZATION = "organization"
    PROJECT = "project"
    GLOBAL = "global"


class PolicyEffect(StrEnum):
    """Per docs/032 "POLICY ENGINE": "Allow" / "Deny"."""

    ALLOW = "allow"
    DENY = "deny"


class PolicyStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    DRAFT = "draft"


class PolicyConditionType(StrEnum):
    """Per docs/032 "POLICY ENGINE": Time/Location/IP/scope/custom rules."""

    TIME_BASED = "time_based"
    LOCATION_BASED = "location_based"
    IP_BASED = "ip_based"
    ORGANIZATION_SCOPE = "organization_scope"
    PROJECT_SCOPE = "project_scope"
    RESOURCE_SCOPE = "resource_scope"
    CUSTOM = "custom"


class AuthorizationDecision(StrEnum):
    ALLOW = "allow"
    DENY = "deny"


__all__ = [
    "AssignmentStatus",
    "AuthorizationDecision",
    "PermissionAction",
    "PermissionGroupCategory",
    "PermissionStatus",
    "PolicyConditionType",
    "PolicyEffect",
    "PolicyStatus",
    "ResourceType",
    "RoleStatus",
    "RoleType",
    "SubjectType",
]
