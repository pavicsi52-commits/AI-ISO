"""``compliance_frameworks``, ``compliance_controls``, and their mappings.

The catalogue an organization is measured against. Frameworks own
controls; controls map to each other across frameworks so that one
assessment can answer several standards at once.

**Controls are versioned, frameworks are not.** A framework's identity
is its published standard -- ISO 27001 is ISO 27001 -- while the text,
severity, and applicability of an individual control genuinely change as
an organization's interpretation matures. Storing a version on the
framework instead would force a whole-catalogue fork to reword one
control, and every historical finding would then point at a control that
no longer exists.
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import (
    JSON,
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import (
    ControlCategory,
    ControlRelationKind,
    ControlSeverity,
    ControlStatus,
    FrameworkCode,
    FrameworkKind,
    FrameworkStatus,
)


class ComplianceFramework(BaseModel):
    """``compliance_frameworks`` -- one standard an organization tracks."""

    __tablename__ = "compliance_frameworks"
    __table_args__ = (
        UniqueConstraint("organization_id", "slug", name="uq_compliance_framework_slug"),
        Index("ix_compliance_framework_org", "organization_id", "status"),
        Index("ix_compliance_framework_code", "organization_id", "code"),
    )

    slug: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    code: Mapped[FrameworkCode] = mapped_column(String(64), index=True)
    kind: Mapped[FrameworkKind] = mapped_column(String(32))
    status: Mapped[FrameworkStatus] = mapped_column(
        String(32), default=FrameworkStatus.DRAFT, index=True
    )

    publisher: Mapped[str | None] = mapped_column(String(255), default=None)
    framework_version: Mapped[str] = mapped_column(String(64), default="1.0.0")
    """The *standard's* version -- "2022" for ISO 27001:2022 -- not a row
    version. Named in full because a bare ``version`` would shadow the
    base entity's integer optimistic-lock column and turn every write
    into a ``TypeError``."""

    reference_url: Mapped[str | None] = mapped_column(String(1_024), default=None)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    """Shipped with the platform. Built-in frameworks and their controls
    cannot be edited, only extended -- an organization that reworded
    NIST 800-53 would report against something that is not NIST 800-53
    while still calling it that."""

    weight: Mapped[float] = mapped_column(Float, default=1.0)
    control_count: Mapped[int] = mapped_column(Integer, default=0)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ComplianceControl(BaseModel):
    """``compliance_controls`` -- one requirement inside a framework."""

    __tablename__ = "compliance_controls"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "framework_id", "code", name="uq_compliance_control_code"
        ),
        Index("ix_compliance_control_framework", "organization_id", "framework_id", "status"),
        Index("ix_compliance_control_category", "organization_id", "category"),
        Index("ix_compliance_control_owner", "organization_id", "owner_id"),
    )

    framework_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("compliance_frameworks.id", ondelete="CASCADE"), index=True
    )
    code: Mapped[str] = mapped_column(String(128))
    """The identifier the standard itself uses -- ``AC-6``, ``A.9.2.3``,
    ``1.1.1``. Kept verbatim so an auditor can look it up."""

    title: Mapped[str] = mapped_column(String(512))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    guidance: Mapped[str | None] = mapped_column(Text, default=None)

    category: Mapped[ControlCategory] = mapped_column(
        String(64), default=ControlCategory.OTHER, index=True
    )
    severity: Mapped[ControlSeverity] = mapped_column(
        String(32), default=ControlSeverity.MEDIUM, index=True
    )
    status: Mapped[ControlStatus] = mapped_column(
        String(32), default=ControlStatus.NOT_IMPLEMENTED, index=True
    )

    owner_id: Mapped[str | None] = mapped_column(String(255), default=None)
    owner_team: Mapped[str | None] = mapped_column(String(255), default=None)

    control_version: Mapped[int] = mapped_column(Integer, default=1)
    """How many times this control's *content* has been revised. Distinct
    from the base entity's optimistic-lock ``version``, which counts
    every write including status changes."""

    parent_control_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("compliance_controls.id", ondelete="SET NULL"), default=None, index=True
    )
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_automatable: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    """Whether a scanner can decide this control without a human. Drives
    what continuous assessment is allowed to attempt: a control needing
    an interview cannot be failed by a collector that found no data."""

    rule: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    """The machine-checkable form, when :attr:`is_automatable`. Evaluated
    by ``app/rules/`` against collected evidence."""

    remediation_guidance: Mapped[str | None] = mapped_column(Text, default=None)
    references: Mapped[list[str]] = mapped_column(JSON, default=list)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ControlMapping(BaseModel):
    """How one control relates to another, usually across frameworks.

    This is what lets a single assessment answer several standards. ISO
    27001 A.9.2.3 and NIST 800-53 AC-6 ask the same question about
    privileged access; evaluating the estate separately for each would
    cost twice as much and, worse, could return contradictory answers
    that nobody could reconcile.
    """

    __tablename__ = "compliance_control_mappings"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "source_control_id",
            "target_control_id",
            "relation",
            name="uq_compliance_control_mapping",
        ),
        Index("ix_compliance_mapping_source", "organization_id", "source_control_id"),
        Index("ix_compliance_mapping_target", "organization_id", "target_control_id"),
    )

    source_control_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("compliance_controls.id", ondelete="CASCADE"), index=True
    )
    target_control_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("compliance_controls.id", ondelete="CASCADE"), index=True
    )
    relation: Mapped[ControlRelationKind] = mapped_column(
        String(32), default=ControlRelationKind.RELATED_TO
    )
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    """How sure the mapping is, 0.0-1.0. An equivalence asserted by the
    standards bodies is 1.0; one inferred by an organization is not, and
    a report that treats the two identically is overstating its
    coverage."""

    note: Mapped[str | None] = mapped_column(Text, default=None)


__all__ = ["ComplianceControl", "ComplianceFramework", "ControlMapping"]
