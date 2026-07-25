"""``user_import_jobs`` table.

Per docs/031 "IMPORT": CSV, Excel, JSON, Bulk Import, Validation,
Duplicate Detection, Error Report, Preview, Rollback. Reuses
:class:`shared_core.enums.job_status.JobStatus` for ``status`` rather
than a service-local enum, matching every other queue/scheduler-backed
job in this codebase.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from shared_core.enums.job_status import JobStatus
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ImportFormat


class UserImportJob(BaseModel):
    """One bulk user-import run, from upload through completion."""

    __tablename__ = "user_import_jobs"

    requested_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    source_format: Mapped[ImportFormat] = mapped_column(String(16))
    source_storage_key: Mapped[str] = mapped_column(String(1024))
    status: Mapped[JobStatus] = mapped_column(String(32), default=JobStatus.PENDING, index=True)
    preview_only: Mapped[bool] = mapped_column(Boolean, default=False)
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    processed_rows: Mapped[int] = mapped_column(Integer, default=0)
    succeeded_rows: Mapped[int] = mapped_column(Integer, default=0)
    failed_rows: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_rows: Mapped[int] = mapped_column(Integer, default=0)
    error_report: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    created_user_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    rolled_back_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["UserImportJob"]
