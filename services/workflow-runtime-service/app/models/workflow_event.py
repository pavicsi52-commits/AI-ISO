"""``workflow_events`` table -- a persisted copy of every
``shared_core.workflow.events.WorkflowEvent`` this service's own engine
run produces.

The SDK publishes these purely in-memory via the engine's own
``on_event`` callback (``EventHandler = Callable[[WorkflowEvent],
Awaitable[None]]``) -- nothing about them survives past that one
callback invocation unless a caller persists it. This table is that
persistence, backing docs/042's own "EVENTS" section list and "AUDIT"
"Workflow Execution" requirement; the same events are also republished
onto ``packages/shared-core/events`` (the RabbitMQ-backed platform
event bus, "Integrate with Prompt 020") from the same callback -- this
table is the durable, queryable local history, the bus is for
cross-service fan-out.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column


class WorkflowEventRecord(BaseModel):
    """One persisted workflow runtime event."""

    __tablename__ = "workflow_events"

    instance_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


__all__ = ["WorkflowEventRecord"]
