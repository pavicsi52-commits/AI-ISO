"""``connector_marketplace``."""

from __future__ import annotations

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ConnectorCategory, MarketplaceStatus


class ConnectorMarketplaceEntry(BaseModel):
    """``connector_marketplace`` -- one installable connector *type* in the catalog.

    One row per distinct connector this platform knows how to model
    (``"aws"``, ``"github"``, ``"prometheus"``, ...) -- ``Connector``
    rows are organization-owned *instances* of one of these. ``built_in``
    entries are seeded once, idempotently, at startup (see
    ``MarketplaceService.seed_builtin_catalog``) from docs/058's own
    "BUILT-IN CONNECTORS" list; non-built-in entries are published
    through ``POST /integrations/marketplace/publish``.
    """

    __tablename__ = "connector_marketplace"
    __table_args__ = (UniqueConstraint("organization_id", "slug", name="uq_marketplace_slug"),)

    slug: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(128))
    category: Mapped[ConnectorCategory] = mapped_column(String(32), index=True)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    publisher: Mapped[str] = mapped_column(String(128), default="AI-IOS")
    built_in: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[MarketplaceStatus] = mapped_column(
        String(16), default=MarketplaceStatus.PUBLISHED, index=True
    )
    latest_version_number: Mapped[str] = mapped_column(String(32), default="1.0.0")
    supported_auth_methods: Mapped[list[str]] = mapped_column(JSON, default=list)
    dependencies: Mapped[list[str]] = mapped_column(JSON, default=list)
    """Other ``connector_marketplace`` rows' own ``slug``s this entry depends on."""
    icon_url: Mapped[str | None] = mapped_column(String(2048), default=None)
    homepage_url: Mapped[str | None] = mapped_column(String(2048), default=None)
    install_count: Mapped[int] = mapped_column(Integer, default=0)
    rating_total: Mapped[float] = mapped_column(Float, default=0.0)
    rating_count: Mapped[int] = mapped_column(Integer, default=0)
    published_by: Mapped[str | None] = mapped_column(String(128), default=None)


__all__ = ["ConnectorMarketplaceEntry"]
