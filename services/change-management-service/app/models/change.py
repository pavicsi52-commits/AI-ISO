"""``change_requests`` and ``change_relationships``.

The core record, and how changes relate to each other -- a dependency
graph over changes, not a chat feature.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import (
    ChangeCategory,
    ChangePriority,
    ChangeStatus,
    ChangeType,
    RelationshipKind,
    RiskLevel,
)


class ChangeRequest(BaseModel):
    """``change_requests`` -- one proposed or in-flight change."""

    __tablename__ = "change_requests"
    __table_args__ = (
        UniqueConstraint("organization_id", "reference", name="uq_change_reference"),
        Index("ix_change_org_status", "organization_id", "status"),
        Index("ix_change_org_priority", "organization_id", "priority"),
        Index("ix_change_org_created", "organization_id", "created_at"),
        Index("ix_change_assignee", "organization_id", "technical_owner_id"),
    )

    reference: Mapped[str] = mapped_column(String(64))
    """A human-quotable identifier -- ``CHG-0042``. What gets read aloud
    in a CAB meeting, unlike a UUID."""

    title: Mapped[str] = mapped_column(String(512))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    business_justification: Mapped[str | None] = mapped_column(Text, default=None)

    requester_id: Mapped[str] = mapped_column(String(255))
    business_owner_id: Mapped[str | None] = mapped_column(String(255), default=None)
    technical_owner_id: Mapped[str | None] = mapped_column(String(255), default=None)

    category: Mapped[ChangeCategory] = mapped_column(
        String(64), default=ChangeCategory.CUSTOM, index=True
    )
    change_type: Mapped[ChangeType] = mapped_column(
        String(32), default=ChangeType.NORMAL, index=True
    )
    priority: Mapped[ChangePriority] = mapped_column(
        String(32), default=ChangePriority.MEDIUM, index=True
    )
    status: Mapped[ChangeStatus] = mapped_column(String(32), default=ChangeStatus.DRAFT, index=True)
    risk_level: Mapped[RiskLevel | None] = mapped_column(String(32), default=None, index=True)
    """Set once a risk assessment has actually run -- ``NULL`` here is
    not LOW, it is "not yet assessed", and callers must not confuse the
    two."""

    affected_assets: Mapped[list[str]] = mapped_column(JSON, default=list)
    affected_services: Mapped[list[str]] = mapped_column(JSON, default=list)
    affected_applications: Mapped[list[str]] = mapped_column(JSON, default=list)
    """Opaque external identifiers -- asset, service, and application
    ids as this platform's other services define them. This service
    does not own that inventory, only which of it a change touches."""

    implementation_plan: Mapped[str | None] = mapped_column(Text, default=None)
    validation_plan: Mapped[str | None] = mapped_column(Text, default=None)
    rollback_plan: Mapped[str | None] = mapped_column(Text, default=None)
    attachments: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)

    cab_required: Mapped[bool] = mapped_column(Boolean, default=False)
    """Set once, at risk assessment time, from the risk level and the
    change type's own policy -- see ``app/changes/engine.py
    ::requires_cab_review``. Stored rather than recomputed on every
    read, so a later policy change cannot retroactively rewrite what a
    change was actually required to go through."""

    calendar_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("change_calendar.id", ondelete="SET NULL"), default=None
    )
    """No ``use_alter`` needed here, unlike Prompt 052's
    ``Incident.major_incident_id``: ``ChangeCalendarEntry`` carries no
    foreign key back to ``ChangeRequest``, so ``change_calendar`` has no
    dependency on this table existing first -- a plain one-directional
    reference, not a cycle."""

    incident_id: Mapped[str | None] = mapped_column(String(64), default=None, index=True)
    problem_id: Mapped[str | None] = mapped_column(String(64), default=None)
    known_error_id: Mapped[str | None] = mapped_column(String(64), default=None)
    """Opaque references into ``services/incident-management-service``'s
    own database, not foreign keys -- the two services do not share a
    database, and an emergency change exists specifically to answer "an
    incident forced this."""

    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    """Set when the change's approval chain (and CAB review, if one was
    required) resolves -- the moment that actually unblocks scheduling,
    not the moment a caller happened to invoke ``schedule()``."""

    scheduled_start_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None, index=True
    )
    scheduled_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    actual_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    actual_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    approval_duration_seconds: Mapped[float | None] = mapped_column(Float, default=None)
    implementation_duration_seconds: Mapped[float | None] = mapped_column(Float, default=None)

    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ChangeRelationship(BaseModel):
    """``change_relationships`` -- how one change relates to another.

    Directional: *change* relates to *related_change* as *kind*
    describes, e.g. change A ``DEPENDS_ON`` change B. The inverse is not
    stored as its own row -- a reader who needs "what depends on this
    change" queries by ``related_change_id`` instead of trusting a
    second row to have been kept in sync with the first.
    """

    __tablename__ = "change_relationships"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "change_id",
            "related_change_id",
            "kind",
            name="uq_change_relationship",
        ),
        Index("ix_change_relationship_change", "organization_id", "change_id"),
        Index("ix_change_relationship_related", "organization_id", "related_change_id"),
    )

    change_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("change_requests.id", ondelete="CASCADE"), index=True
    )
    related_change_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("change_requests.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[RelationshipKind] = mapped_column(String(32), index=True)
    note: Mapped[str | None] = mapped_column(Text, default=None)


__all__ = ["ChangeRelationship", "ChangeRequest"]
