"""seed default system project roles

Per docs/034 "PROJECT ROLES": Owner, Administrator, Operator, Automation
Engineer, Validation Engineer, Developer, Viewer, Auditor. Seeds all
eight as global system roles (``project_id IS NULL``, ``is_system=True``)
using the fixed, deterministic ids in
``app.models.project_role.SYSTEM_ROLE_IDS`` -- every AI-IOS deployment's
"Owner" project role is the same row identity, mirroring
``services/rbac-service``'s identical seeded-system-role precedent.
Their ``organization_id`` is set to the well-known default-organization
placeholder (``00000000-0000-0000-0000-000000000001``) every AI-IOS
service uses for a row that isn't really organization-scoped, the same
choice that seed migration makes for its own system rows.

Revision ID: c1d2e3f4a5b6
Revises: b2384689c56f
Create Date: 2026-07-23 09:00:00.000000

"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c1d2e3f4a5b6"
down_revision: str | Sequence[str] | None = "b2384689c56f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_ORGANIZATION_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")

_SYSTEM_ROLES: list[tuple[str, str, str, int, str]] = [
    (
        "00000000-0000-0000-0000-000000000201",
        "owner",
        "Owner",
        100,
        "Full control of the project, including deletion and ownership transfer.",
    ),
    (
        "00000000-0000-0000-0000-000000000202",
        "administrator",
        "Administrator",
        90,
        "Manages membership, settings, and resources within the project.",
    ),
    (
        "00000000-0000-0000-0000-000000000203",
        "operator",
        "Operator",
        50,
        "Runs and monitors operational workloads within the project.",
    ),
    (
        "00000000-0000-0000-0000-000000000204",
        "automation_engineer",
        "Automation Engineer",
        50,
        "Builds and deploys automation within the project.",
    ),
    (
        "00000000-0000-0000-0000-000000000205",
        "validation_engineer",
        "Validation Engineer",
        50,
        "Creates and approves validation runs within the project.",
    ),
    (
        "00000000-0000-0000-0000-000000000206",
        "developer",
        "Developer",
        40,
        "Builds and configures project resources.",
    ),
    (
        "00000000-0000-0000-0000-000000000207",
        "viewer",
        "Viewer",
        10,
        "Read-only access to the project.",
    ),
    (
        "00000000-0000-0000-0000-000000000208",
        "auditor",
        "Auditor",
        10,
        "Read-only access to the project's audit trail and activity feed.",
    ),
]


def _common_columns() -> list[sa.ColumnClause[Any]]:
    return [
        sa.column("id", sa.Uuid()),
        sa.column("version", sa.Integer),
        sa.column("organization_id", sa.Uuid()),
        sa.column("project_id", sa.Uuid()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
        sa.column("is_active", sa.Boolean),
    ]


def _common_values(now: datetime) -> dict[str, object]:
    return {
        "version": 1,
        "organization_id": DEFAULT_ORGANIZATION_ID,
        "project_id": None,
        "created_at": now,
        "updated_at": now,
        "is_active": True,
    }


def upgrade() -> None:
    now = datetime.now(UTC)

    roles_table = sa.table(
        "project_roles",
        *_common_columns(),
        sa.column("name", sa.String),
        sa.column("code", sa.String),
        sa.column("rank", sa.Integer),
        sa.column("is_system", sa.Boolean),
        sa.column("description", sa.String),
    )
    op.bulk_insert(
        roles_table,
        [
            {
                "id": uuid.UUID(role_id),
                "name": name,
                "code": code,
                "rank": rank,
                "is_system": True,
                "description": description,
                **_common_values(now),
            }
            for role_id, code, name, rank, description in _SYSTEM_ROLES
        ],
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text("DELETE FROM project_roles WHERE id = ANY(:ids)"),
        {"ids": [uuid.UUID(role_id) for role_id, *_ in _SYSTEM_ROLES]},
    )
