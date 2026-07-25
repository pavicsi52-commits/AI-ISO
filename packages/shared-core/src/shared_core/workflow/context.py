"""Workflow execution context.

Per docs/028_Enterprise_Workflow_SDK.md.txt "CONTEXT": Workflow
Context, Execution Context, User Context, Organization Context,
Project Context, Connector Context, AI Context, Plugin Context.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from shared_core.workflow.variables import VariableStore


def new_execution_id() -> str:
    """Generate a new, unique workflow execution id."""
    return str(uuid.uuid4())


@dataclass(slots=True)
class WorkflowContext:
    """Everything one workflow execution needs to know about itself and its caller."""

    workflow_id: str
    execution_id: str = field(default_factory=new_execution_id)
    user_id: str | None = None
    organization_id: str | None = None
    project_id: str | None = None
    variables: VariableStore = field(default_factory=VariableStore)
    connector_context: dict[str, Any] = field(default_factory=dict)
    ai_context: dict[str, Any] = field(default_factory=dict)
    plugin_context: dict[str, Any] = field(default_factory=dict)
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    correlation_id: str | None = None

    def child(self, *, node_id: str) -> WorkflowContext:
        """Build a child context for a nested scope (sub-workflow/parallel branch/loop iteration).

        Shares this context's identity fields but gets its own
        independent :class:`~shared_core.workflow.variables.VariableStore`
        snapshot ("Scoped Variables") and a correlation id extended with
        *node_id*, so nested execution can't accidentally mutate the
        parent's variables.
        """
        return WorkflowContext(
            workflow_id=self.workflow_id,
            execution_id=self.execution_id,
            user_id=self.user_id,
            organization_id=self.organization_id,
            project_id=self.project_id,
            variables=self.variables.child(),
            connector_context=dict(self.connector_context),
            ai_context=dict(self.ai_context),
            plugin_context=dict(self.plugin_context),
            correlation_id=f"{self.correlation_id or self.execution_id}:{node_id}",
        )


__all__ = ["WorkflowContext", "new_execution_id"]
