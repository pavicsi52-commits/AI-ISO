"""``automation_outputs`` table -- captured key/value results produced
by an execution or one of its steps (register variables, command
stdout parse results), consumed by downstream steps/workflow callbacks
per docs/040 "WORKFLOW INTEGRATION" "Shared Variables".
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column


class AutomationOutput(BaseModel):
    """One captured output value produced during an automation execution."""

    __tablename__ = "automation_outputs"

    execution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("automation_executions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("automation_execution_steps.id", ondelete="SET NULL"), default=None, index=True
    )
    key: Mapped[str] = mapped_column(String(255), index=True)
    value: Mapped[Any] = mapped_column(JSON, default=None)


__all__ = ["AutomationOutput"]
