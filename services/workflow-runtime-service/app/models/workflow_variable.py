"""``workflow_variables`` table -- one named variable value.

``instance_id`` is nullable: a ``NULL`` row is a *definition-level*
default (mirroring ``WorkflowDefinition.default_variables``, persisted
per-variable here for individual query/audit rather than only as one
opaque JSON blob), while a non-``NULL`` row is a specific instance's own
resolved runtime value (mirroring
``shared_core.workflow.context.WorkflowContext.variables``, a
:class:`~shared_core.workflow.variables.VariableStore`). ``is_secret``
marks a value that must never be rendered in a REST response or log
line (docs/042 "SECRETS": "Secrets SHALL never appear in logs") --
enforced at the schema/serialization layer, never by omitting the
column here, since resuming a checkpointed run genuinely needs the real
value.
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import WorkflowVariableScope


class WorkflowVariable(BaseModel):
    """One named variable value, at definition or instance scope."""

    __tablename__ = "workflow_variables"

    definition_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_definitions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    instance_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workflow_instances.id", ondelete="CASCADE"), default=None, index=True
    )
    scope: Mapped[WorkflowVariableScope] = mapped_column(
        String(16), default=WorkflowVariableScope.WORKFLOW
    )
    name: Mapped[str] = mapped_column(String(255), index=True)
    value: Mapped[Any] = mapped_column(JSON)
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False)


__all__ = ["WorkflowVariable"]
