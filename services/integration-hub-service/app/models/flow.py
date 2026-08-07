"""``connector_flows``."""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import FlowRunStatus, FlowStatus, FlowTrigger


class ConnectorFlow(BaseModel):
    """``connector_flows`` -- one integration flow definition, plus its own latest run state.

    Docs/058's own "DATABASE TABLES" section lists no separate
    flow-run-history table, so the most recent execution's own outcome
    lives directly on this row (``last_run_status``/``last_run_at``/
    ``run_count``); a full execution trail is published through
    ``connector_events``/``FlowExecutedEvent`` instead of persisted here.
    """

    __tablename__ = "connector_flows"
    __table_args__ = (Index("ix_connector_flow_connector", "connector_id"),)

    connector_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("connectors.id", ondelete="CASCADE"), default=None, index=True
    )
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    definition: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    """The step graph -- a JSON ``{"steps": [...]}`` document evaluated
    by ``app/flows/engine.py``; each step's own ``"kind"`` is one of
    ``FlowStepKind``."""
    status: Mapped[FlowStatus] = mapped_column(String(16), default=FlowStatus.DRAFT, index=True)
    trigger: Mapped[FlowTrigger] = mapped_column(String(16), default=FlowTrigger.MANUAL)
    schedule_interval_seconds: Mapped[int | None] = mapped_column(Integer, default=None)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    last_run_status: Mapped[FlowRunStatus] = mapped_column(
        String(24), default=FlowRunStatus.NEVER_RUN
    )
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    run_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, default=None)


__all__ = ["ConnectorFlow"]
