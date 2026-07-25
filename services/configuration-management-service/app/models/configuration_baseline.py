"""``configuration_baselines`` table. Per docs/039 "BASELINES"
"Support": Golden Images, Golden Configuration, Compliance Baselines,
Security Baselines, Performance Baselines, Vendor Baselines, Custom
Baselines, Version History.
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import BaselineType


class ConfigurationBaseline(BaseModel):
    """One golden/compliance/security/performance/vendor/custom baseline."""

    __tablename__ = "configuration_baselines"

    profile_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("configuration_profiles.id", ondelete="SET NULL"), default=None, index=True
    )
    baseline_type: Mapped[BaselineType] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(String(2048), default=None)
    baseline_version: Mapped[str] = mapped_column(String(32), default="1.0.0")
    content: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


__all__ = ["ConfigurationBaseline"]
