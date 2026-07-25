"""``configuration_assignments`` table -- which managed assets a
profile targets, per docs/039's own "Target Assets"/``ConfigurationAssigned``
naming. ``managed_asset_id`` references
``services/asset-management-service``'s own ``ManagedAsset.id`` --
not a SQL foreign key, since that table lives in a separate service's
database, the same cross-service-reference shape
``services/asset-management-service``'s own ``inventory_asset_id``
already established.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ConfigurationAssignmentStatus


class ConfigurationAssignment(BaseModel):
    """One managed asset's assignment to a configuration profile."""

    __tablename__ = "configuration_assignments"
    __table_args__ = (
        UniqueConstraint(
            "profile_id", "managed_asset_id", name="uq_configuration_assignment_profile_asset"
        ),
    )

    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("configuration_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    managed_asset_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    status: Mapped[ConfigurationAssignmentStatus] = mapped_column(
        String(16), default=ConfigurationAssignmentStatus.PENDING, index=True
    )
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


__all__ = ["ConfigurationAssignment"]
