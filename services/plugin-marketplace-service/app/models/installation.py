"""``plugin_installations``."""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import InstallationTrigger, PluginInstallationStatus


class PluginInstallation(BaseModel):
    """``plugin_installations`` -- one organization's own installed instance
    of a published plugin.

    Deliberately separate from ``Plugin`` (the authoring/publishing
    organization's own definition) so Org A can author and publish a
    plugin while Org B independently installs, configures, upgrades, and
    removes its own copy -- the exact ``Connector``/
    ``ConnectorMarketplaceEntry`` split integration-hub-service (Prompt
    058) already established.
    """

    __tablename__ = "plugin_installations"
    __table_args__ = (
        UniqueConstraint("organization_id", "plugin_id", name="uq_plugin_installation_org"),
        Index("ix_plugin_installation_status", "status"),
    )

    plugin_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("plugins.id", ondelete="CASCADE"), index=True
    )
    installed_version_number: Mapped[str] = mapped_column(String(32))
    status: Mapped[PluginInstallationStatus] = mapped_column(
        String(20), default=PluginInstallationStatus.INSTALLING, index=True
    )
    trigger: Mapped[InstallationTrigger] = mapped_column(
        String(16), default=InstallationTrigger.ONLINE
    )
    configuration: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    installed_by: Mapped[str | None] = mapped_column(String(128), default=None)
    installed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    last_error: Mapped[str | None] = mapped_column(String(1024), default=None)


__all__ = ["PluginInstallation"]
