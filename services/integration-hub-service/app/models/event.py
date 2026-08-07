"""``connector_events``."""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import EventRoutingStatus, EventSource


class ConnectorEvent(BaseModel):
    """``connector_events`` -- one event raised through, or by, a connector."""

    __tablename__ = "connector_events"
    __table_args__ = (Index("ix_connector_event_connector", "connector_id"),)

    connector_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("connectors.id", ondelete="SET NULL"), default=None, index=True
    )
    source: Mapped[EventSource] = mapped_column(String(24), default=EventSource.INTERNAL)
    event_type: Mapped[str] = mapped_column(String(128), index=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    routing_status: Mapped[EventRoutingStatus] = mapped_column(
        String(16), default=EventRoutingStatus.PENDING, index=True
    )
    routed_to: Mapped[list[str]] = mapped_column(JSON, default=list)
    correlation_id: Mapped[str | None] = mapped_column(String(64), default=None)


__all__ = ["ConnectorEvent"]
