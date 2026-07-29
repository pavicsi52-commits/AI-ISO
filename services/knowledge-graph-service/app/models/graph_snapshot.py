"""``graph_snapshots`` table -- a restorable copy of the graph."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import GraphFormat, JobStatus


class GraphSnapshot(BaseModel):
    """One snapshot ("Graph Snapshots", "Snapshot Restore").

    The payload is stored inline as bytes rather than in object storage.
    That is a deliberate trade for this service: a snapshot is the thing
    you reach for when the graph is wrong, and depending on a second
    system being healthy at exactly that moment is how a restore path
    fails when it is finally needed. The size ceiling in settings is
    what keeps the choice honest.
    """

    __tablename__ = "graph_snapshots"

    label: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    status: Mapped[JobStatus] = mapped_column(String(16), default=JobStatus.PENDING, index=True)
    snapshot_format: Mapped[GraphFormat] = mapped_column(String(16), default=GraphFormat.JSON)
    node_count: Mapped[int] = mapped_column(Integer, default=0)
    relationship_count: Mapped[int] = mapped_column(Integer, default=0)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), default=None)
    """Digest of the stored payload, so a restore can prove it read what was written."""

    payload: Mapped[bytes | None] = mapped_column(LargeBinary, default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None, index=True
    )
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


__all__ = ["GraphSnapshot"]
