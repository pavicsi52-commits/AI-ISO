"""Multi-tenant scoping mixin."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Mapped, mapped_column


class TenantMixin:
    """Adds ``organization_id``/``project_id`` tenant scoping columns.

    Per docs/007_Database_Master_Architecture.md.txt: every query must be
    filterable by tenant. ``project_id`` is nullable for
    organization-scoped entities.
    """

    organization_id: Mapped[uuid.UUID] = mapped_column()
    project_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
