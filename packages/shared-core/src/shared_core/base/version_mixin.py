"""Optimistic concurrency version mixin."""

from __future__ import annotations

from sqlalchemy.orm import Mapped, mapped_column


class VersionMixin:
    """Adds a ``version`` column used for optimistic locking.

    Per docs/007_Database_Master_Architecture.md.txt: update statements
    validate the version to detect concurrent modification.
    """

    version: Mapped[int] = mapped_column(default=1)
