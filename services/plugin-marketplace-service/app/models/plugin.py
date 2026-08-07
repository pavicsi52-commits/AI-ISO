"""``plugins`` and ``plugin_versions``."""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import PluginCategory, PluginLifecycleStatus, PluginType


class Plugin(BaseModel):
    """``plugins`` -- one registered plugin definition, owned by its own
    authoring/publishing organization.

    Distinct from ``PluginInstallation`` (a *different* organization's
    own installed instance of a published plugin) -- the same
    "definition owned by its author, instance owned by its installer"
    split ``ConnectorMarketplaceEntry``/``Connector`` already established
    in integration-hub-service (Prompt 058).
    """

    __tablename__ = "plugins"
    __table_args__ = (
        UniqueConstraint("organization_id", "slug", name="uq_plugin_slug"),
        Index("ix_plugin_category", "category"),
    )

    slug: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    category: Mapped[PluginCategory] = mapped_column(String(32), index=True)
    plugin_type: Mapped[PluginType] = mapped_column(String(32))
    publisher_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("plugin_publishers.id", ondelete="SET NULL"), default=None, index=True
    )
    status: Mapped[PluginLifecycleStatus] = mapped_column(
        String(20), default=PluginLifecycleStatus.REGISTERED, index=True
    )
    current_version_number: Mapped[str | None] = mapped_column(String(32), default=None)
    """The plugin's own latest published version -- never ``version``,
    which ``BaseEntityMixin`` already reserves for optimistic locking."""
    homepage_url: Mapped[str | None] = mapped_column(String(2048), default=None)
    license: Mapped[str | None] = mapped_column(String(128), default=None)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    owner_id: Mapped[str | None] = mapped_column(String(128), default=None)


class PluginVersion(BaseModel):
    """``plugin_versions`` -- one immutable, published snapshot of a plugin.

    ``version_number``, not ``version`` -- the same reserved-column
    collision this build has hit and fixed repeatedly (Prompts 047, 033,
    056, 057, and Prompt 058's own ``ConnectorVersion``).
    """

    __tablename__ = "plugin_versions"
    __table_args__ = (
        UniqueConstraint("plugin_id", "version_number", name="uq_plugin_version_number"),
    )

    plugin_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("plugins.id", ondelete="CASCADE"), index=True
    )
    version_number: Mapped[str] = mapped_column(String(32))
    changelog: Mapped[str | None] = mapped_column(Text, default=None)
    compatibility_constraint: Mapped[str] = mapped_column(String(64), default="*")
    """A ``shared_core.plugins.versioning``-compatible specifier (e.g.
    ``">=1.0.0,<2.0.0"``) this version's own platform-version requirement."""
    entry_points: Mapped[list[str]] = mapped_column(JSON, default=list)
    configuration_schema: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    api_requirements: Mapped[list[str]] = mapped_column(JSON, default=list)
    health_checks: Mapped[list[str]] = mapped_column(JSON, default=list)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    released_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    released_by: Mapped[str | None] = mapped_column(String(128), default=None)


__all__ = ["Plugin", "PluginVersion"]
