"""Cross-cutting constants for the authentication service."""

from __future__ import annotations

from uuid import UUID

# Every entity inheriting shared_core.database.base.BaseModel carries a
# mandatory (non-nullable) organization_id, per docs/018's tenant-scoping
# contract -- but docs/030 explicitly excludes Organizations from this
# prompt's scope ("DO NOT IMPLEMENT": Organizations), and no Organization
# service exists yet to mint real ids. Self-registered users are placed in
# this fixed, well-known default organization until a real Organization
# service (a later prompt) replaces it; the column is a bare UUID with no
# foreign key (per BaseEntityMixin's own cross-service-safe convention),
# so this placeholder never needs a real row to reference.
DEFAULT_ORGANIZATION_ID = UUID("00000000-0000-0000-0000-000000000001")

__all__ = ["DEFAULT_ORGANIZATION_ID"]
