"""``report_archives`` table -- immutable retained copies of exports."""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ArchiveStatus, ExportFormat


class ReportArchive(BaseModel):
    """One archived report artifact.

    **Immutable by policy, per docs/047 "Immutable Archive".** The
    archive keeps its own copy of the checksum and bytes rather than
    pointing at the live export row, so purging or regenerating a
    report cannot retroactively alter what was archived. That is the
    entire point of an archive a compliance auditor can rely on.

    ``retention_until`` is stored per row rather than derived from a
    global policy, so a policy change never silently shortens the
    retention of something already archived.
    """

    __tablename__ = "report_archives"

    execution_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("report_executions.id", ondelete="SET NULL"), default=None, index=True
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("report_jobs.id", ondelete="SET NULL"), default=None, index=True
    )
    title: Mapped[str] = mapped_column(String(512), index=True)
    export_format: Mapped[ExportFormat] = mapped_column(String(16), index=True)
    filename: Mapped[str] = mapped_column(String(512))
    content_type: Mapped[str] = mapped_column(String(128))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    checksum_sha256: Mapped[str] = mapped_column(String(64), index=True)
    archive_version: Mapped[int] = mapped_column(Integer, default=1)
    """This artifact's generation within its title's own history.

    Deliberately **not** named ``version``: :class:`BaseModel` already
    owns a ``version`` column for optimistic locking, which
    ``BaseRepository.update()`` increments on every write. Shadowing it
    made archive generations jump on unrelated updates *and* silently
    disabled optimistic locking for this table -- a real bug caught by
    a test that archived, purged, and re-archived.
    """
    status: Mapped[ArchiveStatus] = mapped_column(
        String(16), default=ArchiveStatus.ACTIVE, index=True
    )
    archived_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    retention_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None, index=True
    )
    purge_reason: Mapped[str | None] = mapped_column(Text, default=None)
    content: Mapped[bytes] = mapped_column()


__all__ = ["ReportArchive"]
