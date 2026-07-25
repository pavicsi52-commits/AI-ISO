"""``asset_compliance`` table. Per docs/038 "COMPLIANCE" "Support":
Security, Configuration, License, Patch, Industry, Internal Policies
Compliance; Compliance Reports; Exceptions.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ComplianceStatus, ComplianceType


class AssetCompliance(BaseModel):
    """One compliance-type evaluation recorded against a managed asset."""

    __tablename__ = "asset_compliance"

    managed_asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("managed_assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    compliance_type: Mapped[ComplianceType] = mapped_column(String(24), index=True)
    status: Mapped[ComplianceStatus] = mapped_column(
        String(24), default=ComplianceStatus.UNKNOWN, index=True
    )
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    exception_reason: Mapped[str | None] = mapped_column(String(1024), default=None)


__all__ = ["AssetCompliance"]
