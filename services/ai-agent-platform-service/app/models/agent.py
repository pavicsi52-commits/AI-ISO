"""``agents`` and ``agent_versions``."""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import AgentLifecycleStatus, AgentType


class Agent(BaseModel):
    """``agents`` -- one registered agent definition, owned by its own
    authoring organization.

    Distinct from any future organization's own installed/activated
    *instance* of this agent -- docs/060's own 17-table list has no
    separate installation table the way ``services/plugin-marketplace
    -service``'s own ``PluginInstallation`` does, so one organization's
    own agent is both its definition and its only instance here.
    """

    __tablename__ = "agents"
    __table_args__ = (
        UniqueConstraint("organization_id", "slug", name="uq_agent_slug"),
        Index("ix_agent_type", "agent_type"),
    )

    slug: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    agent_type: Mapped[AgentType] = mapped_column(String(32), index=True)
    status: Mapped[AgentLifecycleStatus] = mapped_column(
        String(20), default=AgentLifecycleStatus.REGISTERED, index=True
    )
    current_version_number: Mapped[str | None] = mapped_column(String(32), default=None)
    """The agent's own latest activated profile snapshot -- never
    ``version``, which ``BaseEntityMixin`` already reserves for
    optimistic locking."""
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    owner_id: Mapped[str | None] = mapped_column(String(128), default=None)
    consecutive_failures: Mapped[int] = mapped_column(default=0)
    last_executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class AgentVersion(BaseModel):
    """``agent_versions`` -- one immutable, activated snapshot of an
    agent's own configuration profile.

    ``version_number``, not ``version`` -- the same reserved-column
    collision this build has hit and fixed repeatedly since Prompt 033.
    """

    __tablename__ = "agent_versions"
    __table_args__ = (
        UniqueConstraint("agent_id", "version_number", name="uq_agent_version_number"),
    )

    agent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), index=True
    )
    version_number: Mapped[str] = mapped_column(String(32))
    changelog: Mapped[str | None] = mapped_column(Text, default=None)
    profile_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    released_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    released_by: Mapped[str | None] = mapped_column(String(128), default=None)


__all__ = ["Agent", "AgentVersion"]
