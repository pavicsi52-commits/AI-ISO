"""``graph_sync_jobs`` table -- one synchronization run against one source."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ConflictResolution, SyncMode, SyncSource, SyncStatus


class GraphSyncJob(BaseModel):
    """One run of the synchronization engine against one source.

    A row per *run*, not per source: "when did inventory last sync, and
    did it work?" is answered by the newest row, while the history stays
    intact for anyone asking why the graph drifted last Tuesday.

    ``consecutive_failures`` lives here rather than being recomputed
    because the engine disables a source after N failures in a row, and
    deriving that by walking history on every tick would grow with the
    table.
    """

    __tablename__ = "graph_sync_jobs"

    source: Mapped[SyncSource] = mapped_column(String(24), index=True)
    mode: Mapped[SyncMode] = mapped_column(String(16), default=SyncMode.INCREMENTAL, index=True)
    status: Mapped[SyncStatus] = mapped_column(String(16), default=SyncStatus.PENDING, index=True)
    conflict_resolution: Mapped[ConflictResolution] = mapped_column(
        String(16), default=ConflictResolution.SOURCE_WINS
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None, index=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    duration_ms: Mapped[float | None] = mapped_column(Float, default=None)
    cursor: Mapped[str | None] = mapped_column(String(255), default=None)
    """Where the last incremental run got to, so the next one resumes.

    An incremental sync that always restarts from the beginning is a
    full sync wearing a different name.
    """

    nodes_created: Mapped[int] = mapped_column(Integer, default=0)
    nodes_updated: Mapped[int] = mapped_column(Integer, default=0)
    nodes_deleted: Mapped[int] = mapped_column(Integer, default=0)
    relationships_created: Mapped[int] = mapped_column(Integer, default=0)
    relationships_deleted: Mapped[int] = mapped_column(Integer, default=0)
    conflicts_detected: Mapped[int] = mapped_column(Integer, default=0)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


__all__ = ["GraphSyncJob"]
