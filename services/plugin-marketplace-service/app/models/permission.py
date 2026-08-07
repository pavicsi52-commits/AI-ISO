"""``plugin_permissions``."""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import PermissionGrantStatus, PluginPermissionCategory


class PluginPermissionGrant(BaseModel):
    """``plugin_permissions`` -- one capability an installed plugin requests
    (and an org either grants, denies, or revokes).

    Bespoke, not a reuse of ``shared_core.plugins.permissions
    .PluginPermission`` -- that framework's own nine values don't cover
    docs/059's literal eleven (Inventory/Automation/Workflow/Secrets/
    Knowledge-Graph/Monitoring/Notification/API/Filesystem/Network/
    Custom), and it has no DB-persisted grant/revoke history of its own.
    """

    __tablename__ = "plugin_permissions"
    __table_args__ = (
        UniqueConstraint(
            "plugin_installation_id", "category", name="uq_plugin_permission_category"
        ),
        Index("ix_plugin_permission_status", "status"),
    )

    plugin_installation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("plugin_installations.id", ondelete="CASCADE"), index=True
    )
    category: Mapped[PluginPermissionCategory] = mapped_column(String(32), index=True)
    scope: Mapped[str | None] = mapped_column(String(255), default=None)
    """An optional narrowing of the category (e.g. a specific inventory
    resource path), left blank for a whole-category grant."""
    status: Mapped[PermissionGrantStatus] = mapped_column(
        String(16), default=PermissionGrantStatus.PENDING, index=True
    )
    justification: Mapped[str | None] = mapped_column(Text, default=None)
    decided_by: Mapped[str | None] = mapped_column(String(128), default=None)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["PluginPermissionGrant"]
