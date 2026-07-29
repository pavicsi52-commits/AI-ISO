"""``graph_import_jobs`` table -- one bulk import."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import GraphFormat, JobStatus


class GraphImportJob(BaseModel):
    """One import run ("Bulk Import").

    ``rejected`` counts rows the parser refused -- an unknown label, a
    missing id, an edge pointing at a node that is not in the payload.
    Reported rather than silently dropped: an import that says "imported
    900" when the file had 1,000 rows has told you nothing about the
    hundred that vanished.
    """

    __tablename__ = "graph_import_jobs"

    filename: Mapped[str] = mapped_column(String(512))
    import_format: Mapped[GraphFormat] = mapped_column(String(16), index=True)
    status: Mapped[JobStatus] = mapped_column(String(16), default=JobStatus.PENDING, index=True)
    dry_run: Mapped[bool] = mapped_column(Boolean, default=False)
    """Parse and validate without writing, so a bad file is found before it lands."""

    nodes_imported: Mapped[int] = mapped_column(Integer, default=0)
    relationships_imported: Mapped[int] = mapped_column(Integer, default=0)
    rejected: Mapped[int] = mapped_column(Integer, default=0)
    rejections: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    duration_ms: Mapped[float | None] = mapped_column(Float, default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["GraphImportJob"]
