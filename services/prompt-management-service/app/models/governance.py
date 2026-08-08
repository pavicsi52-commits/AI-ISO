"""``prompt_reviews``, ``prompt_approvals``, and ``prompt_security_scans``."""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import (
    ApprovalStatus,
    ReviewDecision,
    ScanStatus,
    SecuritySeverity,
)


class PromptReview(BaseModel):
    """``prompt_reviews`` -- one reviewer's verdict on one revision.

    Reviews attach to a *version*, never to the prompt identity: a
    review says "this exact wording is sound", which stops meaning
    anything the moment the wording changes.
    """

    __tablename__ = "prompt_reviews"
    __table_args__ = (Index("ix_prompt_review_decision", "decision"),)

    prompt_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("prompt_versions.id", ondelete="CASCADE"), index=True
    )
    reviewer_id: Mapped[str] = mapped_column(String(128), index=True)
    decision: Mapped[ReviewDecision] = mapped_column(
        String(24), default=ReviewDecision.PENDING, index=True
    )
    comments: Mapped[str | None] = mapped_column(Text, default=None)
    requested_changes: Mapped[list[str]] = mapped_column(JSON, default=list)
    is_mandatory: Mapped[bool] = mapped_column(Boolean, default=False)
    """ "GOVERNANCE": Mandatory Reviews -- a review the approval gate
    will not proceed without, distinct from an advisory one."""
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class PromptApproval(BaseModel):
    """``prompt_approvals`` -- one approval gate on one revision.

    Multi-approver support is by row count, not by a list column:
    ``required_approvals`` says how many distinct ``APPROVED`` rows the
    gate needs, so who approved and when is individually auditable
    rather than collapsed into an array.
    """

    __tablename__ = "prompt_approvals"
    __table_args__ = (
        Index("ix_prompt_approval_status", "status"),
        Index("ix_prompt_approval_expires_at", "expires_at"),
    )

    prompt_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("prompt_versions.id", ondelete="CASCADE"), index=True
    )
    approver_id: Mapped[str | None] = mapped_column(String(128), default=None, index=True)
    status: Mapped[ApprovalStatus] = mapped_column(
        String(16), default=ApprovalStatus.PENDING, index=True
    )
    required_approvals: Mapped[int] = mapped_column(Integer, default=1)
    reason: Mapped[str | None] = mapped_column(Text, default=None)
    requested_by: Mapped[str | None] = mapped_column(String(128), default=None)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    """Backs the approval-expiry sweep. An approval request that sits
    unanswered forever is worse than one that visibly lapses -- the
    former silently blocks a publish with no signal that anything is
    wrong."""


class PromptSecurityScan(BaseModel):
    """``prompt_security_scans`` -- one security scan of one revision.

    ``status`` distinguishes ``BLOCKED`` from ``FLAGGED``: a scan that
    ran correctly and found a critical problem is a different event
    from one that merely raised a concern, and only the former stops a
    publish.
    """

    __tablename__ = "prompt_security_scans"
    __table_args__ = (
        Index("ix_prompt_security_scan_status", "status"),
        Index("ix_prompt_security_scan_severity", "highest_severity"),
    )

    prompt_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("prompt_versions.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[ScanStatus] = mapped_column(String(16), default=ScanStatus.CLEAN, index=True)
    highest_severity: Mapped[SecuritySeverity] = mapped_column(
        String(16), default=SecuritySeverity.INFO, index=True
    )
    findings: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    """Each entry carries ``finding``, ``severity``, and a
    ``description``. **Never the matched text itself** -- a scan row
    recording the secret it found would defeat the point of detecting
    it."""
    finding_count: Mapped[int] = mapped_column(Integer, default=0)
    scanned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    scanned_by: Mapped[str | None] = mapped_column(String(128), default=None)
    blocked_publish: Mapped[bool] = mapped_column(Boolean, default=False)


__all__ = ["PromptApproval", "PromptReview", "PromptSecurityScan"]
