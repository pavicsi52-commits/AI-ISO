"""``workflow_instances`` table -- one particular run of a workflow
version.

``sdk_execution_id`` is ``shared_core.workflow.WorkflowContext
.execution_id``/``WorkflowExecution.execution_id`` -- the SDK's own
string identity for a single in-process run, generated fresh by
:func:`shared_core.workflow.new_execution_id` when a run starts and
carried through every event/checkpoint the SDK produces during that
run. This row's own ``id`` (a UUID, per ``BaseModel``) is this
service's own durable identity, stable across the SDK's purely
in-process ``WorkflowRuntime``/``WorkflowManager`` never surviving a
restart (see ``app/services/execution.py``'s own module docstring) --
every REST/DB reference to "an instance" uses this row's ``id``, never
``sdk_execution_id`` directly.

``parent_instance_id`` supports "Nested Workflows"/"Recursive
Workflows" (docs/042 "WORKFLOW EXECUTION"): a ``SUB_WORKFLOW`` node's
handler creates a child instance row pointing back at the instance that
spawned it -- a field with no equivalent named field in docs/042's own
DATABASE TABLES list, added via direct design reasoning (the same
"found via design reasoning, fixed before it could become a bug"
precedent ``AutomationTarget.username`` and
``PlaybookRepositoryFolder``'s own renaming already established), since
without it a nested workflow's own execution history would be
indistinguishable from an unrelated top-level run.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import WorkflowInstanceStatus, WorkflowTriggerType


class WorkflowInstance(BaseModel):
    """One execution run of a workflow version."""

    __tablename__ = "workflow_instances"

    definition_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_definitions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    parent_instance_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workflow_instances.id", ondelete="SET NULL"), default=None, index=True
    )
    sdk_execution_id: Mapped[str | None] = mapped_column(String(64), default=None, index=True)
    status: Mapped[WorkflowInstanceStatus] = mapped_column(
        String(16), default=WorkflowInstanceStatus.CREATED, index=True
    )
    trigger_type: Mapped[WorkflowTriggerType] = mapped_column(
        String(16), default=WorkflowTriggerType.MANUAL
    )
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    error_message: Mapped[str | None] = mapped_column(Text, default=None)


__all__ = ["WorkflowInstance"]
