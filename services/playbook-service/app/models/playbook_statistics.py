"""``playbook_statistics`` table -- a cached analytics rollup for one
organization. Per docs/041 "ANALYTICS" "Collect": Playbook Count,
Execution References, Downloads, Approvals, Validation Results, Version
Growth, Most Used Content, Deprecated Content. Recomputed periodically
rather than aggregated live on every request, matching
``services/automation-service``'s own ``automation_statistics``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class PlaybookStatistics(BaseModel):
    """One organization's cached playbook-repository analytics snapshot."""

    __tablename__ = "playbook_statistics"
    __table_args__ = (UniqueConstraint("organization_id", name="uq_playbook_statistics_org"),)

    total_playbooks: Mapped[int] = mapped_column(Integer, default=0)
    total_versions: Mapped[int] = mapped_column(Integer, default=0)
    total_downloads: Mapped[int] = mapped_column(Integer, default=0)
    approvals_summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    validation_results_summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    version_growth: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    most_used_content: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    deprecated_content_count: Mapped[int] = mapped_column(Integer, default=0)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


__all__ = ["PlaybookStatistics"]
