"""``incident_postmortems`` and its action items.

The document a review produces, and the commitments that come out of
it. Action items get their own table beyond docs/052's explicit list --
the spec names "Action Items / Owners / Due Dates / Verification" as
things a postmortem supports, and those only function relationally as
rows with their own owner, due date, and status, the same way Prompt
051 added ``compliance_control_mappings`` to make a named feature
("Control Mapping") actually work.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ActionItemStatus, PostmortemStatus


class Postmortem(BaseModel):
    """``incident_postmortems`` -- the post-incident review document."""

    __tablename__ = "incident_postmortems"
    __table_args__ = (Index("ix_postmortem_incident", "organization_id", "incident_id"),)

    incident_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[PostmortemStatus] = mapped_column(
        String(32), default=PostmortemStatus.DRAFT, index=True
    )

    executive_summary: Mapped[str | None] = mapped_column(Text, default=None)
    timeline_summary: Mapped[str | None] = mapped_column(Text, default=None)
    root_cause_summary: Mapped[str | None] = mapped_column(Text, default=None)
    impact_summary: Mapped[str | None] = mapped_column(Text, default=None)
    lessons_learned: Mapped[str | None] = mapped_column(Text, default=None)

    is_blameless: Mapped[bool] = mapped_column(default=True)
    """Stated explicitly and defaulted true. A postmortem's value comes
    from people describing what actually happened, including their own
    mistakes; a culture that punishes that answer gets a postmortem that
    stops being honest, which is a worse outcome than not writing one."""

    author_id: Mapped[str | None] = mapped_column(String(255), default=None)
    reviewers: Mapped[list[str]] = mapped_column(JSON, default=list)
    approved_by: Mapped[str | None] = mapped_column(String(255), default=None)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class PostmortemActionItem(BaseModel):
    """One committed follow-up from a postmortem, owned and dated."""

    __tablename__ = "incident_postmortem_action_items"
    __table_args__ = (
        Index("ix_action_item_postmortem", "organization_id", "postmortem_id"),
        Index("ix_action_item_owner", "organization_id", "owner_id"),
    )

    postmortem_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("incident_postmortems.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(512))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    status: Mapped[ActionItemStatus] = mapped_column(
        String(32), default=ActionItemStatus.OPEN, index=True
    )

    owner_id: Mapped[str | None] = mapped_column(String(255), default=None)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    verified_by: Mapped[str | None] = mapped_column(String(255), default=None)
    """A completed action item is not the same claim as a verified one --
    "we changed the runbook" and "somebody confirmed the runbook is
    actually correct now" are different statements, and only the second
    should let a recurring-incident count treat the gap as closed."""


__all__ = ["Postmortem", "PostmortemActionItem"]
