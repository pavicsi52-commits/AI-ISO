"""Cross-cutting constants for the organization service."""

from __future__ import annotations

from uuid import UUID

# Every entity inheriting shared_core.database.base.BaseModel carries a
# mandatory (non-nullable) organization_id, per docs/018's tenant-scoping
# contract -- including the ``Organization`` entity itself, since "no
# future entity may redefine these fields" per BaseEntityMixin's own
# docstring. An organization's own ``organization_id`` is therefore set
# equal to its own ``id`` at creation (see
# ``app/services/organization.py``'s ``create()``), the well-known
# self-referential pattern for a multi-tenant system's tenant "root"
# entity. This particular value is deliberately the exact same
# placeholder UUID every other AI-IOS service's own
# ``DEFAULT_ORGANIZATION_ID`` already uses -- this service seeds a real
# ``organizations`` row with this id (see the seed migration), so what
# was a bare placeholder everywhere else becomes a real, resolvable
# organization here.
DEFAULT_ORGANIZATION_ID = UUID("00000000-0000-0000-0000-000000000001")

__all__ = ["DEFAULT_ORGANIZATION_ID"]
