"""``agent_tools``."""

from __future__ import annotations

from datetime import datetime

from shared_core.database.base import BaseModel
from shared_core.enums.health_status import HealthStatus
from sqlalchemy import JSON, Boolean, DateTime, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import PermissionCategory, ToolKind


class AgentTool(BaseModel):
    """``agent_tools`` -- the tool registry: one callable capability an
    agent may invoke during execution, per docs/060's own "TOOL
    REGISTRY" section. Distinct from an installable/versioned
    marketplace artifact (unlike ``services/plugin-marketplace
    -service``'s own ``Plugin``) -- a tool is invoked *during* an
    agent's own execution, never installed on its own.
    """

    __tablename__ = "agent_tools"
    __table_args__ = (UniqueConstraint("organization_id", "tool_key", name="uq_agent_tool_key"),)

    tool_key: Mapped[str] = mapped_column(String(128), index=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    tool_kind: Mapped[ToolKind] = mapped_column(String(24), index=True)
    category: Mapped[str] = mapped_column(String(64), default="general")
    parameters_schema: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    required_permission: Mapped[PermissionCategory] = mapped_column(
        String(24), default=PermissionCategory.TOOL_INVOCATION
    )
    is_mutating: Mapped[bool] = mapped_column(Boolean, default=False)
    version_number: Mapped[str] = mapped_column(String(32), default="1.0.0")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_deprecated: Mapped[bool] = mapped_column(Boolean, default=False)
    health_status: Mapped[HealthStatus] = mapped_column(String(16), default=HealthStatus.UNKNOWN)
    last_health_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSON, default=dict)


__all__ = ["AgentTool"]
