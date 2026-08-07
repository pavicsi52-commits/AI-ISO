"""``connector_sync_jobs``."""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ConflictResolution, SyncMode, SyncStatus, SyncTrigger


class ConnectorSyncJob(BaseModel):
    """``connector_sync_jobs`` -- one synchronization run."""

    __tablename__ = "connector_sync_jobs"
    __table_args__ = (Index("ix_connector_sync_job_connector", "connector_id"),)

    connector_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("connectors.id", ondelete="CASCADE"), index=True
    )
    mode: Mapped[SyncMode] = mapped_column(String(16), default=SyncMode.ONE_WAY)
    trigger: Mapped[SyncTrigger] = mapped_column(String(16), default=SyncTrigger.MANUAL)
    status: Mapped[SyncStatus] = mapped_column(String(24), default=SyncStatus.PENDING, index=True)
    conflict_resolution: Mapped[ConflictResolution] = mapped_column(
        String(16), default=ConflictResolution.SOURCE_WINS
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    records_processed: Mapped[int] = mapped_column(Integer, default=0)
    records_succeeded: Mapped[int] = mapped_column(Integer, default=0)
    records_failed: Mapped[int] = mapped_column(Integer, default=0)
    checkpoint: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    """The last-processed cursor/offset -- read back by a resumed run
    picking up where a prior partial run left off (docs/058's own
    "Checkpointing" / "Resume")."""
    triggered_by: Mapped[str | None] = mapped_column(String(128), default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)


__all__ = ["ConnectorSyncJob"]
