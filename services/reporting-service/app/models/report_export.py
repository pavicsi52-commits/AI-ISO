"""``report_exports`` table -- one rendered artifact of one execution."""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ExportFormat


class ReportExport(BaseModel):
    """One rendered file.

    An execution can produce several exports -- the same run delivered
    as both PDF and XLSX -- so the bytes live here, keyed by format,
    rather than on the execution row.

    ``content`` holds the artifact directly. Object storage is a
    *distribution channel* (see :class:`app.models.report_distribution
    .ReportDistribution`), not the system of record: a report must stay
    downloadable and archivable even if MinIO is unreachable, and
    reports are small relative to the media files object storage exists
    for.
    """

    __tablename__ = "report_exports"

    execution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("report_executions.id", ondelete="CASCADE"), index=True
    )
    export_format: Mapped[ExportFormat] = mapped_column(String(16), index=True)
    filename: Mapped[str] = mapped_column(String(512))
    content_type: Mapped[str] = mapped_column(String(128))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    checksum_sha256: Mapped[str] = mapped_column(String(64), index=True)
    download_count: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[bytes] = mapped_column()


__all__ = ["ReportExport"]
