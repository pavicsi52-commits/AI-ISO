"""``asset_reports`` table. Per docs/038 "REPORTING" "Generate": Asset,
Cost, Compliance, Warranty, Maintenance, Risk, Lifecycle Reports,
Executive Dashboards. :attr:`managed_asset_id` is nullable since most
report types (e.g. "Executive Dashboards") aggregate across many
assets rather than describing a single one.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ReportType


class AssetReport(BaseModel):
    """One generated asset-management report."""

    __tablename__ = "asset_reports"

    managed_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("managed_assets.id", ondelete="SET NULL"), default=None, index=True
    )
    report_type: Mapped[ReportType] = mapped_column(String(24), index=True)
    generated_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


__all__ = ["AssetReport"]
