"""``agent_marketplace``."""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import AgentMarketplaceListingStatus


class AgentMarketplaceEntry(BaseModel):
    """``agent_marketplace`` -- one agent's own published listing surface,
    separate from ``Agent`` itself (mirroring ``ConnectorMarketplaceEntry``
    /``Connector`` and ``PluginMarketplaceEntry``/``Plugin``'s own
    established split). ``publisher`` is a bare string, matching
    ``ConnectorMarketplaceEntry.publisher``'s own precedent -- docs/060's
    17-table list has no dedicated publisher table the way
    ``plugin-marketplace-service`` does, and no dedicated review table
    either, so rating aggregates live directly on this row.
    """

    __tablename__ = "agent_marketplace"
    __table_args__ = (UniqueConstraint("agent_id", name="uq_agent_marketplace_entry"),)

    agent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[AgentMarketplaceListingStatus] = mapped_column(
        String(16), default=AgentMarketplaceListingStatus.DRAFT, index=True
    )
    featured: Mapped[bool] = mapped_column(Boolean, default=False)
    publisher: Mapped[str] = mapped_column(String(128), default="AI-IOS")
    description: Mapped[str | None] = mapped_column(Text, default=None)
    install_count: Mapped[int] = mapped_column(Integer, default=0)
    rating_total: Mapped[float] = mapped_column(Float, default=0.0)
    rating_count: Mapped[int] = mapped_column(Integer, default=0)
    listed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    approved_by: Mapped[str | None] = mapped_column(String(128), default=None)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    rejection_reason: Mapped[str | None] = mapped_column(Text, default=None)


__all__ = ["AgentMarketplaceEntry"]
