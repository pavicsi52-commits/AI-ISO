"""``workflow_timers`` table -- one scheduled wake-up for a workflow
instance or definition.

Per docs/042 "TIMERS" "Support": Delay, Wait, Cron, Timeout, Scheduled
Resume, Recurring Timers, Event Timeout. ``DELAY``/``TIMER`` node types
are handled entirely *structurally* by the SDK's own executor
(``asyncio.sleep`` -- see ``app/services/execution.py``'s own
docstring) and need no row here; this table instead backs the
process-surviving cases the SDK cannot do on its own: a ``CRON``/
``RECURRING`` schedule that re-triggers a whole workflow via
``shared_core.scheduler`` (see ``app/scheduling/registrar.py``), and an
``EVENT_TIMEOUT`` watchdog for a paused/waiting instance.
``instance_id`` is nullable for a definition-level recurring schedule
that hasn't fired its first instance yet.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import TimerType


class WorkflowTimer(BaseModel):
    """One scheduled wake-up for a workflow instance or definition."""

    __tablename__ = "workflow_timers"

    definition_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_definitions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    instance_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workflow_instances.id", ondelete="CASCADE"), default=None, index=True
    )
    node_id: Mapped[str | None] = mapped_column(String(255), default=None)
    timer_type: Mapped[TimerType] = mapped_column(String(16))
    cron_expression: Mapped[str | None] = mapped_column(String(128), default=None)
    fires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    recurring: Mapped[bool] = mapped_column(Boolean, default=False)
    fired: Mapped[bool] = mapped_column(Boolean, default=False)


__all__ = ["WorkflowTimer"]
