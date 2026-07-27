"""``workflow_context`` table -- one generic key/value slice of a
running instance's own execution context.

Mirrors ``shared_core.workflow.context.WorkflowContext``'s own
``connector_context``/``ai_context``/``plugin_context`` dicts -- opaque,
node-handler-specific state that isn't a workflow *variable* (not
resolved via expressions/conditions, never shown as a "Variable" in any
REST response) but still needs to survive a checkpoint/restore cycle.
``key`` distinguishes the origin dict (``"connector_context"``,
``"ai_context"``, ``"plugin_context"``, or a caller-defined key).
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column


class WorkflowContextEntry(BaseModel):
    """One generic key/value context entry for a workflow instance."""

    __tablename__ = "workflow_context"

    instance_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(String(255), index=True)
    value: Mapped[Any] = mapped_column(JSON)


__all__ = ["WorkflowContextEntry"]
