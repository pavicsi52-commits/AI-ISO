"""Database-layer type aliases."""

from __future__ import annotations

from typing import NamedTuple
from uuid import UUID

type EntityId = UUID


class TenantScope(NamedTuple):
    """The tenant boundary every query must be filtered by.

    Attributes:
        organization_id: Owning organization. Always required.
        project_id: Owning project. ``None`` for organization-scoped entities.
    """

    organization_id: UUID
    project_id: UUID | None = None
