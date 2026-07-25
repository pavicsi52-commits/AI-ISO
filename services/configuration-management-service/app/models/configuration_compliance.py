"""``configuration_compliance`` table. Per docs/039 "COMPLIANCE"
"Evaluate": Security Compliance, Configuration Compliance, Baseline
Compliance, Policy Compliance, Environment Compliance, Industry
Standards, "Generate Compliance Reports".
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ComplianceEvalType, ComplianceStatus


class ConfigurationCompliance(BaseModel):
    """One compliance-type evaluation recorded against a configuration profile."""

    __tablename__ = "configuration_compliance"

    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("configuration_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    eval_type: Mapped[ComplianceEvalType] = mapped_column(String(24), index=True)
    status: Mapped[ComplianceStatus] = mapped_column(
        String(24), default=ComplianceStatus.UNKNOWN, index=True
    )
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    exception_reason: Mapped[str | None] = mapped_column(String(1024), default=None)


__all__ = ["ConfigurationCompliance"]
