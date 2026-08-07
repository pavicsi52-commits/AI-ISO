"""``plugin_marketplace``."""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import MarketplaceListingStatus


class PluginMarketplaceEntry(BaseModel):
    """``plugin_marketplace`` -- one plugin's own published listing surface.

    Kept separate from ``Plugin`` (the raw registration row) so a
    plugin can move through Registration -> Validation -> Publishing ->
    Approval (``PluginLifecycleStatus``) while its own marketplace
    listing (searchable, featured, deprecated, removed) is a distinct,
    independently-toggled concern -- mirrors
    ``ConnectorMarketplaceEntry``'s own separation from ``Connector`` in
    integration-hub-service (Prompt 058).
    """

    __tablename__ = "plugin_marketplace"
    __table_args__ = (UniqueConstraint("plugin_id", name="uq_plugin_marketplace_entry"),)

    plugin_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("plugins.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[MarketplaceListingStatus] = mapped_column(
        String(16), default=MarketplaceListingStatus.DRAFT, index=True
    )
    featured: Mapped[bool] = mapped_column(Boolean, default=False)
    search_keywords: Mapped[list[str]] = mapped_column(JSON, default=list)
    install_count: Mapped[int] = mapped_column(Integer, default=0)
    active_install_count: Mapped[int] = mapped_column(Integer, default=0)
    icon_url: Mapped[str | None] = mapped_column(String(2048), default=None)
    screenshots: Mapped[list[str]] = mapped_column(JSON, default=list)
    pricing_summary: Mapped[str | None] = mapped_column(String(255), default=None)
    listed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    approved_by: Mapped[str | None] = mapped_column(String(128), default=None)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    rejection_reason: Mapped[str | None] = mapped_column(Text, default=None)


__all__ = ["PluginMarketplaceEntry"]
