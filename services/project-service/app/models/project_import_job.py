"""``project_import_jobs`` table.

Per docs/034 "IMPORT": JSON, YAML, CSV, ZIP Package, Validation,
Preview, Conflict Detection, Rollback. Not itself named in docs/034's
"DATABASE TABLES" list, but required to back "Background Processing"
and "Rollback" as durable job state -- the same inferred-but-necessary
addition ``services/user-management-service``'s own
``UserImportJob``/``UserExportJob`` pair established for its own
identical import/export requirement. Reuses
:class:`shared_core.enums.job_status.JobStatus` for ``status`` rather
than a service-local enum, matching every other queue-backed job in
this codebase.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from shared_core.enums.job_status import JobStatus
from sqlalchemy import JSON, Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ImportFormat


class ProjectImportJob(BaseModel):
    """One bulk project-import run, from upload through completion."""

    __tablename__ = "project_import_jobs"

    requested_by: Mapped[uuid.UUID] = mapped_column(index=True)
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
    created_project_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    rolled_back_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["ProjectImportJob"]
