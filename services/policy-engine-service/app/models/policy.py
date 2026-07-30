"""``policies``, ``policy_versions``, and ``policy_categories``.

The catalogue itself. A policy carries its rule tree as JSON rather than
as normalised rows, and that is worth explaining: a rule is evaluated as
a *whole tree* on the authorization path, so decomposing it across
``policy_rules`` and ``policy_conditions`` would mean reassembling it
with joins on every decision. The normalised tables exist too --
docs/050 names both -- and hold the authored, individually-addressable
form; :attr:`Policy.compiled_rule` is the evaluation-ready projection
that publishing writes.

**Priority breaks ties within an effect, never between effects.** Two
policies that both allow are ordered by priority; a high-priority allow
never outranks any deny. See
:data:`~app.models.enums.EFFECT_PRECEDENCE` for why that ordering is not
negotiable.
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
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import PolicyCategory, PolicyEffect, PolicyStatus, PolicyType


class PolicyCategoryRecord(BaseModel):
    """``policy_categories`` -- a named grouping an organization defines.

    The :class:`~app.models.enums.PolicyCategory` enum fixes the
    *platform's* categories; this table lets an organization describe
    and organise them without the enum becoming customer data.
    """

    __tablename__ = "policy_categories"
    __table_args__ = (UniqueConstraint("organization_id", "slug", name="uq_policy_category_slug"),)

    slug: Mapped[str] = mapped_column(String(128), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    category: Mapped[PolicyCategory] = mapped_column(
        String(64), default=PolicyCategory.CUSTOM, index=True
    )
    display_order: Mapped[int] = mapped_column(Integer, default=0)


class Policy(BaseModel):
    """``policies`` -- one governance rule the engine evaluates."""

    __tablename__ = "policies"
    __table_args__ = (
        UniqueConstraint("organization_id", "slug", name="uq_policy_slug"),
        # The candidate-selection index. Every evaluation filters on
        # exactly these four columns before loading anything, so this is
        # what keeps decision latency independent of catalogue size.
        Index(
            "ix_policy_evaluation",
            "organization_id",
            "status",
            "category",
            "priority",
        ),
    )

    slug: Mapped[str] = mapped_column(String(128), index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(Text, default=None)

    category: Mapped[PolicyCategory] = mapped_column(
        String(64), default=PolicyCategory.AUTHORIZATION, index=True
    )
    policy_type: Mapped[PolicyType] = mapped_column(String(32), default=PolicyType.RBAC, index=True)
    effect: Mapped[PolicyEffect] = mapped_column(String(32), default=PolicyEffect.DENY, index=True)
    status: Mapped[PolicyStatus] = mapped_column(String(16), default=PolicyStatus.DRAFT, index=True)

    priority: Mapped[int] = mapped_column(Integer, default=100, index=True)
    """Tie-break within one effect. Higher wins; never crosses effects."""

    version: Mapped[str] = mapped_column(String(32), default="1.0.0")
    """Semantic version of the *published* content.

    Named ``version`` in docs/050's sense, and deliberately a string --
    ``BaseEntityMixin`` already owns an integer ``version`` column for
    optimistic locking, and this is the one place in this service where
    the two words would collide. Kept as text so the collision is
    impossible rather than merely unlikely.
    """

    # ---- what this policy applies to ----------------------------------

    subject_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    resource_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    actions: Mapped[list[str]] = mapped_column(JSON, default=list)
    """Empty means "any".

    An empty selector is deliberately permissive in *scope* while the
    effect stays whatever it is: a policy with no resource types and a
    DENY effect denies broadly, which is the correct reading of "this
    applies everywhere". The alternative -- empty means nothing -- would
    make a whole-estate deny impossible to express.
    """

    # ---- how it decides -------------------------------------------------

    compiled_rule: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    """The evaluation-ready rule tree, written at publish time.

    Read on every decision, so it is stored as one document rather than
    reassembled from ``policy_rules`` by join. Publishing is what makes
    an authored change take effect, which is also what gives a reviewer
    a moment to look at it.
    """

    obligations: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    """What must happen for a conditional effect to be satisfied.

    ``REQUIRE_APPROVAL`` names an approval type and approvers here;
    ``REQUIRE_MFA`` names the acceptable methods. Kept with the policy
    rather than derived at decision time so the obligation a caller is
    given is the one the policy author wrote.
    """

    risk_weight: Mapped[float] = mapped_column(Float, default=0.0)
    """How much this policy contributes to a decision's risk score."""

    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    labels: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    is_system: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    """Whether this is a platform-provided policy.

    System policies cannot be deleted, only superseded -- a deployment
    whose baseline guardrails can be removed by an API call does not
    have guardrails.
    """

    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    published_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    evaluation_count: Mapped[int] = mapped_column(Integer, default=0)
    last_evaluated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    """Usage, for finding policies nobody has matched in a year.

    An unmatched policy is either dead weight or a rule whose conditions
    stopped lining up with reality -- and the second is far more
    dangerous, because it looks like governance and enforces nothing.
    """


class PolicyVersion(BaseModel):
    """``policy_versions`` -- an immutable snapshot of published content.

    Written on every publish and never updated. That is what makes
    rollback a real operation rather than a hopeful one: restoring
    points at a row that still holds exactly what was live, instead of
    reconstructing it from a change log.
    """

    __tablename__ = "policy_versions"
    __table_args__ = (
        UniqueConstraint("policy_id", "version", name="uq_policy_version"),
        Index("ix_policy_version_sequence", "policy_id", "sequence"),
    )

    policy_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("policies.id", ondelete="CASCADE"), index=True
    )
    sequence: Mapped[int] = mapped_column(Integer)
    version: Mapped[str] = mapped_column(String(32))

    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    effect: Mapped[PolicyEffect] = mapped_column(String(32), default=PolicyEffect.DENY)
    policy_type: Mapped[PolicyType] = mapped_column(String(32), default=PolicyType.RBAC)
    category: Mapped[PolicyCategory] = mapped_column(
        String(64), default=PolicyCategory.AUTHORIZATION
    )
    priority: Mapped[int] = mapped_column(Integer, default=100)

    subject_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    resource_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    actions: Mapped[list[str]] = mapped_column(JSON, default=list)
    compiled_rule: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    obligations: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    risk_weight: Mapped[float] = mapped_column(Float, default=0.0)

    change_summary: Mapped[str | None] = mapped_column(Text, default=None)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    published_by: Mapped[uuid.UUID | None] = mapped_column(default=None)

    checksum_sha256: Mapped[str | None] = mapped_column(String(64), default=None)
    """Digest of the published content ("Policy integrity verification").

    A stored policy that no longer matches its digest has been changed
    by something that did not go through publishing -- which for the
    service that authorizes everything else is the one tampering signal
    worth having.
    """


__all__ = ["Policy", "PolicyCategoryRecord", "PolicyVersion"]
