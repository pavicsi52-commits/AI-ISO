"""``agent_permissions``."""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import PermissionCategory, PermissionGrantStatus


class AgentPermissionGrant(BaseModel):
    """``agent_permissions`` -- one capability an agent requests (and an
    org either grants, denies, or revokes), mirroring
    ``services/plugin-marketplace-service``'s own
    ``PluginPermissionGrant`` shape with this service's own agent-shaped
    ``PermissionCategory`` taxonomy.
    """

    __tablename__ = "agent_permissions"
    __table_args__ = (
        UniqueConstraint("agent_id", "category", name="uq_agent_permission_category"),
        Index("ix_agent_permission_status", "status"),
    )

    agent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), index=True
    )
    category: Mapped[PermissionCategory] = mapped_column(String(24), index=True)
    scope: Mapped[str | None] = mapped_column(String(255), default=None)
    status: Mapped[PermissionGrantStatus] = mapped_column(
        String(16), default=PermissionGrantStatus.PENDING, index=True
    )
    justification: Mapped[str | None] = mapped_column(Text, default=None)
    decided_by: Mapped[str | None] = mapped_column(String(128), default=None)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["AgentPermissionGrant"]
