"""``plugin_upgrades`` and ``plugin_rollbacks``."""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import RollbackStatus, UpgradeStatus, UpgradeStrategy


class PluginUpgrade(BaseModel):
    """``plugin_upgrades`` -- one installation's own upgrade attempt history."""

    __tablename__ = "plugin_upgrades"
    __table_args__ = (Index("ix_plugin_upgrade_installation", "plugin_installation_id"),)

    plugin_installation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("plugin_installations.id", ondelete="CASCADE"), index=True
    )
    from_version_number: Mapped[str] = mapped_column(String(32))
    to_version_number: Mapped[str] = mapped_column(String(32))
    strategy: Mapped[UpgradeStrategy] = mapped_column(String(16), default=UpgradeStrategy.MANUAL)
    status: Mapped[UpgradeStatus] = mapped_column(
        String(16), default=UpgradeStatus.PENDING, index=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    initiated_by: Mapped[str | None] = mapped_column(String(128), default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)


class PluginRollback(BaseModel):
    """``plugin_rollbacks`` -- one installation's own rollback attempt history."""

    __tablename__ = "plugin_rollbacks"
    __table_args__ = (Index("ix_plugin_rollback_installation", "plugin_installation_id"),)

    plugin_installation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("plugin_installations.id", ondelete="CASCADE"), index=True
    )
    plugin_upgrade_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("plugin_upgrades.id", ondelete="SET NULL"), default=None, index=True
    )
    from_version_number: Mapped[str] = mapped_column(String(32))
    to_version_number: Mapped[str] = mapped_column(String(32))
    status: Mapped[RollbackStatus] = mapped_column(
        String(16), default=RollbackStatus.PENDING, index=True
    )
    reason: Mapped[str | None] = mapped_column(Text, default=None)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    initiated_by: Mapped[str | None] = mapped_column(String(128), default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)


__all__ = ["PluginRollback", "PluginUpgrade"]
