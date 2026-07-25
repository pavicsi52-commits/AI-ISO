"""``discovery_jobs`` table -- one discovery run.

Per docs/037 "DISCOVERY MODES"/"REST APIs". Reuses
``shared_core.enums.job_status.JobStatus``, matching
``services/inventory-service``'s own ``AssetImportJob``/
``AssetExportJob`` precedent for every queue-backed job in this
platform -- not a service-local status enum.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from shared_core.enums.job_status import JobStatus
from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import DiscoveryMode


class DiscoveryJob(BaseModel):
    """One discovery run against one or more targets."""

    __tablename__ = "discovery_jobs"

    profile_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("discovery_profiles.id", ondelete="SET NULL"), default=None
    )
    schedule_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("discovery_schedules.id", ondelete="SET NULL"), default=None
    )
    mode: Mapped[DiscoveryMode] = mapped_column(
        String(16), default=DiscoveryMode.MANUAL, index=True
    )
    status: Mapped[JobStatus] = mapped_column(String(32), default=JobStatus.PENDING, index=True)
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    total_targets: Mapped[int] = mapped_column(Integer, default=0)
    succeeded_targets: Mapped[int] = mapped_column(Integer, default=0)
    failed_targets: Mapped[int] = mapped_column(Integer, default=0)
    discovered_asset_count: Mapped[int] = mapped_column(Integer, default=0)
    discovered_relationship_count: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    error_summary: Mapped[str | None] = mapped_column(String(2048), default=None)


__all__ = ["DiscoveryJob"]
