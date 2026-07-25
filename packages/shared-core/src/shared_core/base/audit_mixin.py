"""Creator/modifier/deleter audit mixin."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Mapped, mapped_column


class AuditMixin:
    """Adds ``created_by``/``updated_by``/``deleted_by`` user reference columns."""

    created_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
