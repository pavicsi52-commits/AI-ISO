"""seed default system roles and permission catalog

Per docs/032 "DEFAULT SYSTEM ROLES" (10 named roles) and "PERMISSION
MODEL"/"PERMISSION ACTIONS"/"RESOURCE TYPES": seeds a complete
permission catalog (every ``ResourceType`` x every ``PermissionAction``,
320 rows) and the 10 system roles, then grants each role a sensible
subset of that catalog matching its name -- Platform Administrator
gets everything, Viewer gets read-only everywhere, Auditor gets
read+audit+monitor everywhere, and so on. Role and permission ids are
deterministic (fixed UUIDs from ``app.constants.SYSTEM_ROLE_IDS`` for
roles, ``uuid5`` of the resource/action pair for permissions) rather
than randomly generated, so every AI-IOS deployment's "Platform
Administrator" row, for example, is the exact same identity.

Revision ID: a1b2c3d4e5f6
Revises: 0f9e46b38696
Create Date: 2026-07-22 21:30:00.000000

"""

import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "0f9e46b38696"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_ORGANIZATION_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")

_PERMISSION_NAMESPACE = uuid.UUID("6f6a1e3e-6f0a-4e9a-8e3b-0f6a1e3e6f0a")

_RESOURCES = [
    "users", "organizations", "projects", "assets", "inventory", "automation",
    "workflows", "validation", "monitoring", "notifications", "reports",
    "dashboards", "plugins", "connectors", "settings", "secrets", "ai",
    "storage", "scheduler", "api_keys",
]  # fmt: skip

_ACTIONS = [
    "create", "read", "update", "delete", "execute", "approve", "import",
    "export", "assign", "manage", "configure", "audit", "monitor",
    "schedule", "deploy", "rollback",
]  # fmt: skip

_PLATFORM_ONLY_RESOURCES = {"settings", "secrets", "plugins", "connectors", "scheduler", "ai"}
_PROJECT_RESOURCES = {
    "projects", "assets", "inventory", "automation", "workflows", "validation",
    "monitoring", "notifications", "reports", "dashboards",
}  # fmt: skip

_ROLES = [
    ("platform_administrator", "Platform Administrator", "Full, unrestricted platform control."),
    (
        "organization_administrator",
        "Organization Administrator",
        "Manages users, projects, and operational resources within an organization.",
    ),
    (
        "project_administrator",
        "Project Administrator",
        "Manages a single project's resources end to end.",
    ),
    ("operator", "Operator", "Runs and monitors operational workloads."),
    (
        "automation_engineer",
        "Automation Engineer",
        "Builds, deploys, and rolls back automation and workflows.",
    ),
    (
        "validation_engineer",
        "Validation Engineer",
        "Creates and approves validation runs against assets and inventory.",
    ),
    ("viewer", "Viewer", "Read-only access across the platform."),
    ("auditor", "Auditor", "Read, audit, and monitor access across the platform."),
    ("api_client", "API Client", "Machine-to-machine read/execute access for integrations."),
    ("service_account", "Service Account", "Automated internal service-to-service operations."),
]

_SYSTEM_ROLE_IDS = {
    "platform_administrator": uuid.UUID("00000000-0000-0000-0000-000000000101"),
    "organization_administrator": uuid.UUID("00000000-0000-0000-0000-000000000102"),
    "project_administrator": uuid.UUID("00000000-0000-0000-0000-000000000103"),
    "operator": uuid.UUID("00000000-0000-0000-0000-000000000104"),
    "automation_engineer": uuid.UUID("00000000-0000-0000-0000-000000000105"),
    "validation_engineer": uuid.UUID("00000000-0000-0000-0000-000000000106"),
    "viewer": uuid.UUID("00000000-0000-0000-0000-000000000107"),
    "auditor": uuid.UUID("00000000-0000-0000-0000-000000000108"),
    "api_client": uuid.UUID("00000000-0000-0000-0000-000000000109"),
    "service_account": uuid.UUID("00000000-0000-0000-0000-000000000110"),
}


def _permission_id(resource: str, action: str) -> uuid.UUID:
    return uuid.uuid5(_PERMISSION_NAMESPACE, f"{resource}:{action}")


def _validation_engineer_grants(resource: str, action: str) -> bool:
    if resource == "validation":
        return action in {"create", "read", "update", "execute", "approve"}
    return resource in {"assets", "inventory"} and action == "read"


_GRANT_RULES: dict[str, Callable[[str, str], bool]] = {
    "platform_administrator": lambda resource, action: True,
    "organization_administrator": lambda resource, action: resource not in _PLATFORM_ONLY_RESOURCES,
    "project_administrator": lambda resource, action: resource in _PROJECT_RESOURCES,
    "operator": lambda resource, action: resource
    in {"automation", "workflows", "monitoring", "assets", "inventory"}
    and action in {"read", "execute", "monitor", "schedule"},
    "automation_engineer": lambda resource, action: resource
    in {"automation", "workflows", "connectors", "plugins"}
    and action
    in {"create", "read", "update", "delete", "execute", "deploy", "rollback", "schedule"},
    "validation_engineer": _validation_engineer_grants,
    "viewer": lambda resource, action: action == "read",
    "auditor": lambda resource, action: action in {"read", "audit", "monitor"},
    "api_client": lambda resource, action: resource in {"automation", "workflows", "ai", "reports"}
    and action in {"read", "execute"},
    "service_account": lambda resource, action: resource
    in {"automation", "workflows", "scheduler", "storage", "ai"}
    and action in {"create", "read", "update", "execute"},
}


def _grants_for(role_code: str, resource: str, action: str) -> bool:
    """Whether *role_code* should be granted *resource*/*action* ("DEFAULT SYSTEM ROLES")."""
    rule = _GRANT_RULES.get(role_code)
    return rule(resource, action) if rule is not None else False


def upgrade() -> None:
    now = datetime.now(UTC)

    permissions_table = sa.table(
        "permissions",
        sa.column("id", sa.Uuid()),
        sa.column("name", sa.String),
        sa.column("code", sa.String),
        sa.column("description", sa.String),
        sa.column("category", sa.String),
        sa.column("resource", sa.String),
        sa.column("action", sa.String),
        sa.column("scope", sa.String),
        sa.column("status", sa.String),
        sa.column("version", sa.Integer),
        sa.column("metadata", sa.JSON),
        sa.column("permission_group_id", sa.Uuid()),
        sa.column("organization_id", sa.Uuid()),
        sa.column("project_id", sa.Uuid()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
        sa.column("is_active", sa.Boolean),
    )
    roles_table = sa.table(
        "roles",
        sa.column("id", sa.Uuid()),
        sa.column("name", sa.String),
        sa.column("code", sa.String),
        sa.column("description", sa.String),
        sa.column("role_type", sa.String),
        sa.column("status", sa.String),
        sa.column("parent_role_id", sa.Uuid()),
        sa.column("is_system", sa.Boolean),
        sa.column("priority", sa.Integer),
        sa.column("metadata", sa.JSON),
        sa.column("version", sa.Integer),
        sa.column("organization_id", sa.Uuid()),
        sa.column("project_id", sa.Uuid()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
        sa.column("is_active", sa.Boolean),
    )
    role_permissions_table = sa.table(
        "role_permissions",
        sa.column("id", sa.Uuid()),
        sa.column("role_id", sa.Uuid()),
        sa.column("permission_id", sa.Uuid()),
        sa.column("granted_by", sa.Uuid()),
        sa.column("version", sa.Integer),
        sa.column("organization_id", sa.Uuid()),
        sa.column("project_id", sa.Uuid()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
        sa.column("is_active", sa.Boolean),
    )

    permission_rows = []
    permission_ids: dict[tuple[str, str], uuid.UUID] = {}
    for resource in _RESOURCES:
        for action in _ACTIONS:
            pid = _permission_id(resource, action)
            permission_ids[(resource, action)] = pid
            permission_rows.append(
                {
                    "id": pid,
                    "name": f"{resource.replace('_', ' ').title()} {action.title()}",
                    "code": f"{resource}:{action}",
                    "description": f"Permission to {action} {resource}.",
                    "category": None,
                    "resource": resource,
                    "action": action,
                    "scope": "global",
                    "status": "active",
                    "version": 1,
                    "metadata": {},
                    "permission_group_id": None,
                    "organization_id": DEFAULT_ORGANIZATION_ID,
                    "project_id": None,
                    "created_at": now,
                    "updated_at": now,
                    "is_active": True,
                }
            )
    op.bulk_insert(permissions_table, permission_rows)

    role_rows = []
    for code, name, description in _ROLES:
        role_rows.append(
            {
                "id": _SYSTEM_ROLE_IDS[code],
                "name": name,
                "code": code,
                "description": description,
                "role_type": "system",
                "status": "active",
                "parent_role_id": None,
                "is_system": True,
                "priority": 0,
                "metadata": {},
                "version": 1,
                "organization_id": DEFAULT_ORGANIZATION_ID,
                "project_id": None,
                "created_at": now,
                "updated_at": now,
                "is_active": True,
            }
        )
    op.bulk_insert(roles_table, role_rows)

    grant_rows = []
    for code, _name, _description in _ROLES:
        role_id = _SYSTEM_ROLE_IDS[code]
        for resource in _RESOURCES:
            for action in _ACTIONS:
                if not _grants_for(code, resource, action):
                    continue
                grant_rows.append(
                    {
                        "id": uuid.uuid4(),
                        "role_id": role_id,
                        "permission_id": permission_ids[(resource, action)],
                        "granted_by": None,
                        "version": 1,
                        "organization_id": DEFAULT_ORGANIZATION_ID,
                        "project_id": None,
                        "created_at": now,
                        "updated_at": now,
                        "is_active": True,
                    }
                )
    op.bulk_insert(role_permissions_table, grant_rows)


def downgrade() -> None:
    bind = op.get_bind()
    role_ids = list(_SYSTEM_ROLE_IDS.values())
    bind.execute(
        sa.text("DELETE FROM role_permissions WHERE role_id IN :ids").bindparams(
            sa.bindparam("ids", expanding=True)
        ),
        {"ids": role_ids},
    )
    bind.execute(
        sa.text("DELETE FROM roles WHERE id IN :ids").bindparams(
            sa.bindparam("ids", expanding=True)
        ),
        {"ids": role_ids},
    )
    bind.execute(
        sa.text("DELETE FROM permissions WHERE organization_id = :org_id"),
        {"org_id": DEFAULT_ORGANIZATION_ID},
    )
