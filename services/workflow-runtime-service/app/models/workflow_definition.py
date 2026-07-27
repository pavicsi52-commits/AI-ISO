"""``workflow_definitions`` table -- the reusable workflow content
definition.

Per docs/042 "WORKFLOW EXECUTION": a workflow definition is metadata
plus a pointer to its own *current*
:class:`~app.models.workflow_version.WorkflowVersion` -- the actual
DAG (nodes/edges) lives in that version snapshot, never inline here,
the same definition/content-snapshot split
``services/playbook-service``'s own
``Playbook``/``PlaybookVersion`` pair established.

``workflow_key`` is the stable business identifier passed as
``shared_core.workflow.WorkflowDefinition.workflow_id`` when a version
is compiled -- distinct from this row's own database ``id`` (a
definition can be renamed/recreated across environments while the SDK
still needs one durable string identity per logical workflow).

``current_version_number`` (a version *string*, e.g. ``"1.2.0"``) is
deliberately not named ``version`` -- that name is already
``BaseModel``'s own inherited optimistic-concurrency integer column,
the same precedent ``Playbook.current_version`` already established.
"""

from __future__ import annotations

from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column


class WorkflowDefinition(BaseModel):
    """One reusable workflow definition."""

    __tablename__ = "workflow_definitions"

    workflow_key: Mapped[str] = mapped_column(String(255), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    owner: Mapped[str | None] = mapped_column(String(255), default=None)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    default_variables: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    current_version_number: Mapped[str | None] = mapped_column(String(32), default=None)


__all__ = ["WorkflowDefinition"]
