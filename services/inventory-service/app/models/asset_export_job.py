"""``asset_export_jobs`` table.

Per docs/036 "EXPORT": CSV, Excel, JSON, YAML, PDF, ZIP, Background
Processing, Audit. See ``app/models/asset_import_job.py``'s docstring
for the shared ``JobStatus`` reuse rationale.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from shared_core.enums.job_status import JobStatus
from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ExportFormat


class AssetExportJob(BaseModel):
    """One bulk asset-export run, from request through completion."""

    __tablename__ = "asset_export_jobs"

    requested_by: Mapped[uuid.UUID] = mapped_column(index=True)
    target_format: Mapped[ExportFormat] = mapped_column(String(16))
    filter_criteria: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[JobStatus] = mapped_column(String(32), default=JobStatus.PENDING, index=True)
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    result_storage_key: Mapped[str | None] = mapped_column(String(1024), default=None)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["AssetExportJob"]
