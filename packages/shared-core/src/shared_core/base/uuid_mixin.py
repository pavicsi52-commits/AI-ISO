"""UUID primary key mixin."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Mapped, mapped_column


class UUIDMixin:
    """Adds a server-side-generated UUID v4 primary key.

    Per docs/007_Database_Master_Architecture.md.txt: every table uses a
    UUID primary key, never an integer auto-increment.
    """

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
