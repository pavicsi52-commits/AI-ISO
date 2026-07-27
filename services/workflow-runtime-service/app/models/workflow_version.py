"""``workflow_versions`` table -- one immutable DAG snapshot of a
workflow definition.

``nodes``/``edges`` are the JSON-serialized shape
``shared_core.workflow.parser.parse_dict`` consumes directly (a list of
``{node_id, node_type, name, config, timeout_seconds, retryable}``/
``{from, to, condition, label}`` mappings) -- this row is reconstructed
into a real ``shared_core.workflow.WorkflowDefinition`` via
``app/services/compiler.py`` before every compile/run, never executed
from this row's own JSON directly. ``compiled_execution_plan`` caches
``shared_core.workflow.dag.execution_plan``'s own topological "levels"
output (a ``list[list[str]]`` of node ids) computed once at creation
time via ``shared_core.workflow.compiler.compile_workflow``, so a
request that only needs to *display* the plan (not run it) never has
to recompile it, mirroring ``WorkflowManager.compiled_workflow``'s own
per-version caching described in its own docstring.
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column


class WorkflowVersion(BaseModel):
    """One immutable DAG snapshot of a workflow definition."""

    __tablename__ = "workflow_versions"

    definition_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_definitions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[str] = mapped_column(String(32), index=True)
    nodes: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    edges: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    compiled_execution_plan: Mapped[list[list[str]]] = mapped_column(JSON)


__all__ = ["WorkflowVersion"]
