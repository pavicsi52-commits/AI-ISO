"""``change_tasks``, ``change_implementations``, ``change_validations``, ``change_rollbacks``.

The four tables that track a change from "ready to start" through
whatever actually happened -- the individual work items, the
implementation run as a whole, what was checked before and after, and
what had to be undone.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import (
    ChangeTaskStatus,
    ImplementationStatus,
    RollbackStatus,
    ValidationKind,
    ValidationStatus,
)


class ChangeTask(BaseModel):
    """``change_tasks`` -- one unit of implementation work."""

    __tablename__ = "change_tasks"
    __table_args__ = (Index("ix_change_task_change", "organization_id", "change_id", "sequence"),)

    change_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("change_requests.id", ondelete="CASCADE"), index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str] = mapped_column(String(512))
    description: Mapped[str | None] = mapped_column(Text, default=None)

    assignee_id: Mapped[str | None] = mapped_column(String(255), default=None)
    status: Mapped[ChangeTaskStatus] = mapped_column(
        String(32), default=ChangeTaskStatus.PENDING, index=True
    )

    automation_reference: Mapped[str | None] = mapped_column(String(255), default=None)
    workflow_reference: Mapped[str | None] = mapped_column(String(255), default=None)
    """Opaque ids into ``services/automation-service`` and
    ``services/workflow-runtime-service`` -- this service tracks that a
    task ran through automation, not how that automation itself works."""

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ChangeImplementation(BaseModel):
    """``change_implementations`` -- one implementation run of a change, as a whole."""

    __tablename__ = "change_implementations"
    __table_args__ = (Index("ix_change_implementation_change", "organization_id", "change_id"),)

    change_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("change_requests.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[ImplementationStatus] = mapped_column(
        String(32), default=ImplementationStatus.NOT_STARTED, index=True
    )
    started_by: Mapped[str | None] = mapped_column(String(255), default=None)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    progress_percent: Mapped[int] = mapped_column(Integer, default=0)
    timeline: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    """An append-only log of what happened during this run -- task
    completions, validation results, anything worth showing on a
    live-implementation timeline -- kept here rather than reconstructed
    from other tables' timestamps at read time."""
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ChangeValidation(BaseModel):
    """``change_validations`` -- one validation run against a change.

    Integrates Prompt 043's validation framework: this row records that
    a validation ran and what it found, not how the check itself is
    implemented.
    """

    __tablename__ = "change_validations"
    __table_args__ = (Index("ix_change_validation_change", "organization_id", "change_id", "kind"),)

    change_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("change_requests.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[ValidationKind] = mapped_column(String(32), index=True)
    status: Mapped[ValidationStatus] = mapped_column(
        String(32), default=ValidationStatus.PENDING, index=True
    )
    summary: Mapped[str | None] = mapped_column(Text, default=None)
    is_gate: Mapped[bool] = mapped_column(Boolean, default=False)
    """Whether a failure here blocks progress rather than merely being
    recorded -- a pre-change gate that fails must stop implementation
    from starting, the same way a post-change gate that fails must stop
    a change from closing out as successful."""

    ran_by: Mapped[str | None] = mapped_column(String(255), default=None)
    ran_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ChangeRollback(BaseModel):
    """``change_rollbacks`` -- undoing a change that did not hold."""

    __tablename__ = "change_rollbacks"
    __table_args__ = (Index("ix_change_rollback_change", "organization_id", "change_id"),)

    change_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("change_requests.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[RollbackStatus] = mapped_column(
        String(32), default=RollbackStatus.PLANNED, index=True
    )
    plan: Mapped[str] = mapped_column(Text)

    triggered_by: Mapped[str | None] = mapped_column(String(255), default=None)
    triggered_reason: Mapped[str] = mapped_column(Text)

    approved_by: Mapped[str | None] = mapped_column(String(255), default=None)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    validation_summary: Mapped[str | None] = mapped_column(Text, default=None)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


__all__ = ["ChangeImplementation", "ChangeRollback", "ChangeTask", "ChangeValidation"]
