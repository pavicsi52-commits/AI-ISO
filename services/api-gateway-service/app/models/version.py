"""``api_versions`` -- one version of one registered service's own API."""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column


class ApiVersion(BaseModel):
    """``api_versions`` -- one version a service exposes (docs/056 "API VERSIONING")."""

    __tablename__ = "api_versions"
    __table_args__ = (Index("ix_api_version_service", "organization_id", "service_id"),)

    service_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("api_services.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[str] = mapped_column(String(32))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_deprecated: Mapped[bool] = mapped_column(Boolean, default=False)
    deprecation_message: Mapped[str | None] = mapped_column(Text, default=None)
    sunset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    migration_guidance: Mapped[str | None] = mapped_column(Text, default=None)


__all__ = ["ApiVersion"]
