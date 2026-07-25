"""seed default organization

Per docs/033 "ORGANIZATION MODEL": seeds a real ``organizations`` row
using the exact same fixed UUID
(``00000000-0000-0000-0000-000000000001``) every other AI-IOS service's
own ``DEFAULT_ORGANIZATION_ID`` placeholder already uses, plus its
default settings/preferences/branding/subscription/license/limits/
quota rows -- what was a bare, unresolvable placeholder UUID everywhere
else becomes a real, resolvable organization here. The organization's
own ``organization_id`` column (mandatory on every AI-IOS entity, per
``shared_core.base.tenant_mixin.TenantMixin``) is set equal to its own
``id`` -- the well-known self-referential pattern for a multi-tenant
system's tenant "root" entity (see ``app/constants.py``'s docstring).

Revision ID: b2c3d4e5f6a7
Revises: 74ae375e3368
Create Date: 2026-07-22 22:00:00.000000

"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: str | Sequence[str] | None = "74ae375e3368"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_ORGANIZATION_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


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

    organizations_table = sa.table(
        "organizations",
        *_common_columns(),
        sa.column("name", sa.String),
        sa.column("display_name", sa.String),
        sa.column("short_name", sa.String),
        sa.column("slug", sa.String),
        sa.column("description", sa.String),
        sa.column("status", sa.String),
        sa.column("primary_domain", sa.String),
        sa.column("primary_contact_email", sa.String),
        sa.column("logo_url", sa.String),
        sa.column("website", sa.String),
        sa.column("industry", sa.String),
        sa.column("timezone", sa.String),
        sa.column("language", sa.String),
        sa.column("country", sa.String),
        sa.column("currency", sa.String),
        sa.column("metadata", sa.JSON),
    )
    op.bulk_insert(
        organizations_table,
        [
            {
                "id": DEFAULT_ORGANIZATION_ID,
                "name": "Default Organization",
                "display_name": "Default Organization",
                "short_name": "Default",
                "slug": "default",
                "description": (
                    "The default AI-IOS tenant, used until real organizations are " "provisioned."
                ),
                "status": "active",
                "primary_domain": None,
                "primary_contact_email": None,
                "logo_url": None,
                "website": None,
                "industry": None,
                "timezone": "UTC",
                "language": "en",
                "country": None,
                "currency": "USD",
                "metadata": {},
                **_common_values(now),
            }
        ],
    )

    settings_table = sa.table(
        "organization_settings",
        *_common_columns(),
        sa.column("password_policy", sa.JSON),
        sa.column("mfa_enforced", sa.Boolean),
        sa.column("allowed_domains", sa.JSON),
        sa.column("default_language", sa.String),
        sa.column("default_timezone", sa.String),
        sa.column("session_timeout_minutes", sa.Integer),
        sa.column("data_retention_days", sa.Integer),
        sa.column("storage_policy", sa.JSON),
        sa.column("notification_policy", sa.JSON),
    )
    op.bulk_insert(
        settings_table,
        [
            {
                "id": uuid.uuid4(),
                "password_policy": {},
                "mfa_enforced": False,
                "allowed_domains": [],
                "default_language": "en",
                "default_timezone": "UTC",
                "session_timeout_minutes": 60,
                "data_retention_days": 365,
                "storage_policy": {},
                "notification_policy": {},
                **_common_values(now),
            }
        ],
    )

    preferences_table = sa.table(
        "organization_preferences",
        *_common_columns(),
        sa.column("dashboard_layout", sa.JSON),
        sa.column("notification_preferences", sa.JSON),
        sa.column("ui_preferences", sa.JSON),
    )
    op.bulk_insert(
        preferences_table,
        [
            {
                "id": uuid.uuid4(),
                "dashboard_layout": {},
                "notification_preferences": {},
                "ui_preferences": {},
                **_common_values(now),
            }
        ],
    )

    branding_table = sa.table(
        "organization_branding",
        *_common_columns(),
        sa.column("logo_url", sa.String),
        sa.column("dark_logo_url", sa.String),
        sa.column("favicon_url", sa.String),
        sa.column("primary_color", sa.String),
        sa.column("secondary_color", sa.String),
        sa.column("theme", sa.String),
        sa.column("email_templates", sa.JSON),
        sa.column("login_screen_branding", sa.JSON),
        sa.column("dashboard_branding", sa.JSON),
    )
    op.bulk_insert(
        branding_table,
        [
            {
                "id": uuid.uuid4(),
                "logo_url": None,
                "dark_logo_url": None,
                "favicon_url": None,
                "primary_color": "#0F62FE",
                "secondary_color": "#161616",
                "theme": "light",
                "email_templates": {},
                "login_screen_branding": {},
                "dashboard_branding": {},
                **_common_values(now),
            }
        ],
    )

    subscriptions_table = sa.table(
        "organization_subscriptions",
        *_common_columns(),
        sa.column("plan", sa.String),
        sa.column("status", sa.String),
        sa.column("billing_reference", sa.String),
        sa.column("started_at", sa.DateTime(timezone=True)),
        sa.column("renews_at", sa.DateTime(timezone=True)),
        sa.column("expires_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        subscriptions_table,
        [
            {
                "id": uuid.uuid4(),
                "plan": "enterprise",
                "status": "active",
                "billing_reference": None,
                "started_at": now,
                "renews_at": None,
                "expires_at": None,
                **_common_values(now),
            }
        ],
    )

    licenses_table = sa.table(
        "organization_licenses",
        *_common_columns(),
        sa.column("license_type", sa.String),
        sa.column("license_key", sa.String),
        sa.column("seat_count", sa.Integer),
        sa.column("consumed_seats", sa.Integer),
        sa.column("status", sa.String),
        sa.column("activated_at", sa.DateTime(timezone=True)),
        sa.column("expires_at", sa.DateTime(timezone=True)),
        sa.column("grace_period_days", sa.Integer),
    )
    op.bulk_insert(
        licenses_table,
        [
            {
                "id": uuid.uuid4(),
                "license_type": "enterprise",
                "license_key": f"DEFAULT-{DEFAULT_ORGANIZATION_ID}",
                "seat_count": 9_999,
                "consumed_seats": 0,
                "status": "active",
                "activated_at": now,
                "expires_at": None,
                "grace_period_days": 14,
                **_common_values(now),
            }
        ],
    )

    limits_table = sa.table(
        "organization_limits",
        *_common_columns(),
        sa.column("cpu_cores", sa.Integer),
        sa.column("memory_mb", sa.Integer),
        sa.column("storage_gb", sa.Integer),
        sa.column("queue_usage", sa.Integer),
        sa.column("concurrent_workflows", sa.Integer),
        sa.column("concurrent_jobs", sa.Integer),
        sa.column("concurrent_ai_tasks", sa.Integer),
        sa.column("concurrent_users", sa.Integer),
        sa.column("bandwidth_mbps", sa.Integer),
    )
    op.bulk_insert(
        limits_table,
        [
            {
                "id": uuid.uuid4(),
                "cpu_cores": 16,
                "memory_mb": 32_768,
                "storage_gb": 500,
                "queue_usage": 10_000,
                "concurrent_workflows": 100,
                "concurrent_jobs": 100,
                "concurrent_ai_tasks": 50,
                "concurrent_users": 1_000,
                "bandwidth_mbps": 1_000,
                **_common_values(now),
            }
        ],
    )

    quotas_table = sa.table(
        "organization_quotas",
        *_common_columns(),
        sa.column("max_users", sa.Integer),
        sa.column("max_projects", sa.Integer),
        sa.column("max_assets", sa.Integer),
        sa.column("max_storage_gb", sa.Integer),
        sa.column("max_workflows", sa.Integer),
        sa.column("max_automation_jobs", sa.Integer),
        sa.column("max_connectors", sa.Integer),
        sa.column("max_api_calls_per_day", sa.Integer),
        sa.column("max_ai_requests_per_day", sa.Integer),
        sa.column("max_plugins", sa.Integer),
    )
    op.bulk_insert(
        quotas_table,
        [
            {
                "id": uuid.uuid4(),
                "max_users": 9_999,
                "max_projects": 9_999,
                "max_assets": 1_000_000,
                "max_storage_gb": 500,
                "max_workflows": 9_999,
                "max_automation_jobs": 9_999,
                "max_connectors": 9_999,
                "max_api_calls_per_day": 10_000_000,
                "max_ai_requests_per_day": 1_000_000,
                "max_plugins": 9_999,
                **_common_values(now),
            }
        ],
    )


def downgrade() -> None:
    bind = op.get_bind()
    for table in (
        "organization_quotas",
        "organization_limits",
        "organization_licenses",
        "organization_subscriptions",
        "organization_branding",
        "organization_preferences",
        "organization_settings",
        "organizations",
    ):
        bind.execute(
            sa.text(f"DELETE FROM {table} WHERE organization_id = :org_id"),
            {"org_id": DEFAULT_ORGANIZATION_ID},
        )
