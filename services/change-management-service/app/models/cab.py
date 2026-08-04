"""``change_cab`` and ``change_cab_votes``.

The Change Advisory Board review for one change, and the individual
votes that decide it. A votes table sits alongside the one docs/053
names explicitly, for the same reason Prompt 052 added
``incident_war_room_participants`` beside the tables its own spec
listed: "who voted, and how" is exactly the question an audited CAB
decision has to answer, and nowhere else in the schema answers it.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import CabMeetingStatus, CabVote


class ChangeCab(BaseModel):
    """``change_cab`` -- one change's Change Advisory Board review."""

    __tablename__ = "change_cab"
    __table_args__ = (Index("ix_change_cab_change", "organization_id", "change_id"),)

    change_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("change_requests.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[CabMeetingStatus] = mapped_column(
        String(32), default=CabMeetingStatus.SCHEDULED, index=True
    )

    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    held_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    chair_id: Mapped[str | None] = mapped_column(String(255), default=None)

    is_emergency_cab: Mapped[bool] = mapped_column(Boolean, default=False)
    is_virtual: Mapped[bool] = mapped_column(Boolean, default=False)

    agenda: Mapped[str | None] = mapped_column(Text, default=None)
    notes: Mapped[str | None] = mapped_column(Text, default=None)

    quorum_fraction_required: Mapped[float] = mapped_column(default=0.5)
    invited_count: Mapped[int] = mapped_column(default=0)
    quorum_met: Mapped[bool | None] = mapped_column(Boolean, default=None)
    outcome: Mapped[CabVote | None] = mapped_column(String(32), default=None)
    """The board's aggregate decision -- ``None`` until the meeting
    closes and a tally actually runs, never inferred from individual
    votes on the fly."""


class ChangeCabVote(BaseModel):
    """``change_cab_votes`` -- one board member's vote at one review."""

    __tablename__ = "change_cab_votes"
    __table_args__ = (
        UniqueConstraint("organization_id", "cab_id", "voter_id", name="uq_change_cab_vote"),
        Index("ix_change_cab_vote_cab", "organization_id", "cab_id"),
    )

    cab_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("change_cab.id", ondelete="CASCADE"), index=True
    )
    voter_id: Mapped[str] = mapped_column(String(255), index=True)
    vote: Mapped[CabVote] = mapped_column(String(32))
    comment: Mapped[str | None] = mapped_column(Text, default=None)
    voted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


__all__ = ["ChangeCab", "ChangeCabVote"]
