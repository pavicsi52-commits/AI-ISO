"""Cross-cutting constants for the project service."""

from __future__ import annotations

from uuid import UUID

# The well-known placeholder every AI-IOS service uses for a row that
# isn't really organization-scoped -- see
# ``services/organization-service``'s own identical constant, which
# additionally seeds a *real* organization row at this id. Used here
# for import/export job rows, which span potentially many
# organizations (each imported/exported project carries its own real
# ``organization_id``) and so have no single organization of their own.
DEFAULT_ORGANIZATION_ID = UUID("00000000-0000-0000-0000-000000000001")

__all__ = ["DEFAULT_ORGANIZATION_ID"]
