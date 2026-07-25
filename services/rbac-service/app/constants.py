"""Cross-cutting constants for the RBAC service."""

from __future__ import annotations

from uuid import UUID

# Every entity inheriting shared_core.database.base.BaseModel carries a
# mandatory (non-nullable) organization_id, per docs/018's tenant-scoping
# contract -- but docs/032 explicitly excludes Organizations from this
# prompt's scope ("DO NOT IMPLEMENT": Organizations), and no Organization
# service exists yet to mint real ids. Deliberately the exact same value as
# services/authentication-service's and services/user-management-service's
# own DEFAULT_ORGANIZATION_ID, since every service describes the same
# default tenant until a real Organization service exists -- not a
# coincidence to "fix" later.
DEFAULT_ORGANIZATION_ID = UUID("00000000-0000-0000-0000-000000000001")

# Per docs/032 "DEFAULT SYSTEM ROLES" -- fixed, deterministic ids (not
# randomly generated per environment) so every AI-IOS deployment's
# Platform Administrator role, for example, is the exact same row
# identity, referenceable from documentation, fixtures, and other
# services without a lookup-by-code round trip. Seeded by
# alembic/versions' second migration; codes match Role.code exactly.
SYSTEM_ROLE_IDS: dict[str, UUID] = {
    "platform_administrator": UUID("00000000-0000-0000-0000-000000000101"),
    "organization_administrator": UUID("00000000-0000-0000-0000-000000000102"),
    "project_administrator": UUID("00000000-0000-0000-0000-000000000103"),
    "operator": UUID("00000000-0000-0000-0000-000000000104"),
    "automation_engineer": UUID("00000000-0000-0000-0000-000000000105"),
    "validation_engineer": UUID("00000000-0000-0000-0000-000000000106"),
    "viewer": UUID("00000000-0000-0000-0000-000000000107"),
    "auditor": UUID("00000000-0000-0000-0000-000000000108"),
    "api_client": UUID("00000000-0000-0000-0000-000000000109"),
    "service_account": UUID("00000000-0000-0000-0000-000000000110"),
}

__all__ = ["DEFAULT_ORGANIZATION_ID", "SYSTEM_ROLE_IDS"]
