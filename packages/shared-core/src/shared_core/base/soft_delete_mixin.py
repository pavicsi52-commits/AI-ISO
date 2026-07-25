"""Soft delete mixin."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column


class SoftDeleteMixin:
    """Adds ``deleted_at``/``is_active`` columns.

    Per docs/007_Database_Master_Architecture.md.txt: delete operations
    never remove records. They set ``deleted_at`` and ``is_active=false``.
    """

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        default=None,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
