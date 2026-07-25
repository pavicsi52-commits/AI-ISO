"""``discovery_profiles`` table -- reusable scan configuration.

Per docs/037 "DISCOVERY PROFILES": Quick Scan, Deep Scan, Network Scan,
Cloud Scan, Kubernetes Scan, Industrial Scan, Application Scan, Custom
Profiles. A profile bundles which protocols to probe, default ports,
timeout/concurrency limits, and is referenced by both ad-hoc jobs
(``discovery_jobs.profile_id``) and recurring schedules
(``discovery_schedules.profile_id``).
"""

from __future__ import annotations

from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ProfileType


class DiscoveryProfile(BaseModel):
    """One reusable discovery scan configuration."""

    __tablename__ = "discovery_profiles"

    name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(String(2048), default=None)
    profile_type: Mapped[ProfileType] = mapped_column(
        String(24), default=ProfileType.CUSTOM, index=True
    )
    protocols: Mapped[list[str]] = mapped_column(JSON, default=list)
    default_ports: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=30)
    concurrency_limit: Mapped[int] = mapped_column(Integer, default=10)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)


__all__ = ["DiscoveryProfile"]
