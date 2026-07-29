"""``graph_versions`` table -- one recorded version of the graph."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class GraphVersion(BaseModel):
    """One version of an organization graph ("VERSIONING").

    ``sequence`` is a per-organization monotonic counter, deliberately
    **not** named ``version``: that name belongs to
    :class:`BaseModel`'s optimistic-locking column, which
    ``BaseRepository.update()`` increments on every write. Redeclaring
    it has shipped as a live bug twice in this platform.
    """

    __tablename__ = "graph_versions"
    __table_args__ = (
        UniqueConstraint("organization_id", "sequence", name="uq_graph_version_sequence"),
    )

    sequence: Mapped[int] = mapped_column(Integer, index=True)
    label: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    node_count: Mapped[int] = mapped_column(Integer, default=0)
    relationship_count: Mapped[int] = mapped_column(Integer, default=0)
    node_type_counts: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    relationship_type_counts: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(default=None, index=True)
    """The snapshot this version can be restored from, if one was taken.

    Nullable because a version is cheap bookkeeping and a snapshot is
    not: an installation may want a version marker on every sync but a
    full snapshot only nightly.
    """

    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    captured_by: Mapped[uuid.UUID | None] = mapped_column(default=None, index=True)


__all__ = ["GraphVersion"]
