"""Creation/update timestamp mixin."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column


def _utcnow() -> datetime:
    return datetime.now(UTC)


class TimestampMixin:
    """Adds ``created_at``/``updated_at`` columns.

    Per docs/007_Database_Master_Architecture.md.txt: always
    ``TIMESTAMP WITH TIME ZONE``, UTC only.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
    )
