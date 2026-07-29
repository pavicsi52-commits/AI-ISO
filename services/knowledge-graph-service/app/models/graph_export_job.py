"""``graph_export_jobs`` table -- one bulk export."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, Float, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import GraphFormat, JobStatus


class GraphExportJob(BaseModel):
    """One export run ("Bulk Export", "Scheduled Export")."""

    __tablename__ = "graph_export_jobs"

    export_format: Mapped[GraphFormat] = mapped_column(String(16), index=True)
    status: Mapped[JobStatus] = mapped_column(String(16), default=JobStatus.PENDING, index=True)
    filename: Mapped[str] = mapped_column(String(512))
    content_type: Mapped[str] = mapped_column(String(128), default="application/json")
    node_count: Mapped[int] = mapped_column(Integer, default=0)
    relationship_count: Mapped[int] = mapped_column(Integer, default=0)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), default=None)
    payload: Mapped[bytes | None] = mapped_column(LargeBinary, default=None)
    filters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    duration_ms: Mapped[float | None] = mapped_column(Float, default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["GraphExportJob"]
