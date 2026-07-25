"""``configuration_reports`` table. Per docs/039 "REPORTING"
"Generate": Configuration Reports, Compliance Reports, Drift Reports,
Baseline Reports, Version Reports, Approval Reports, Executive
Dashboards.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ConfigReportType


class ConfigurationReport(BaseModel):
    """One generated configuration-management report."""

    __tablename__ = "configuration_reports"

    profile_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("configuration_profiles.id", ondelete="SET NULL"), default=None, index=True
    )
    report_type: Mapped[ConfigReportType] = mapped_column(String(24), index=True)
    generated_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


__all__ = ["ConfigurationReport"]
