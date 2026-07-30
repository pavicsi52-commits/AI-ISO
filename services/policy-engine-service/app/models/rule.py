"""``policy_rules``, ``policy_conditions``, and ``policy_attributes``.

The authored form of a rule tree: individually addressable rows a UI can
edit one at a time, which a single JSON blob cannot offer. Publishing
compiles these into :attr:`~app.models.policy.Policy.compiled_rule`, and
evaluation reads only the compiled form.

**The two forms can disagree, and that is deliberate.** Editing a
condition changes the authored rows immediately and changes nothing
about live decisions until someone publishes. That gap is the review
window; collapsing it -- by evaluating the authored rows directly --
would mean every keystroke in a policy editor was a change to
production authorization.
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import (
    JSON,
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import AttributeSource, LogicalOperator, RuleOperator


class PolicyRule(BaseModel):
    """``policy_rules`` -- one node in a policy's rule tree.

    Self-referential: ``parent_rule_id`` is what gives docs/050's
    "Nested Rules" a storage shape. A rule with no parent is a policy's
    root.
    """

    __tablename__ = "policy_rules"
    __table_args__ = (Index("ix_policy_rule_tree", "policy_id", "parent_rule_id", "display_order"),)

    policy_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("policies.id", ondelete="CASCADE"), index=True
    )
    parent_rule_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("policy_rules.id", ondelete="CASCADE"), default=None, index=True
    )

    name: Mapped[str] = mapped_column(String(255), default="rule")
    description: Mapped[str | None] = mapped_column(Text, default=None)
    logical_operator: Mapped[LogicalOperator] = mapped_column(
        String(8), default=LogicalOperator.ALL
    )
    negate: Mapped[bool] = mapped_column(Boolean, default=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class PolicyCondition(BaseModel):
    """``policy_conditions`` -- one comparison inside a rule."""

    __tablename__ = "policy_conditions"
    __table_args__ = (Index("ix_policy_condition_rule", "rule_id", "display_order"),)

    rule_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("policy_rules.id", ondelete="CASCADE"), index=True
    )
    policy_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("policies.id", ondelete="CASCADE"), index=True
    )
    """Denormalised from the rule.

    Carried so "every condition in this policy" is one query rather than
    a recursive walk of the rule tree -- which is what conflict
    detection and impact analysis both need, over the whole catalogue.
    """

    attribute_source: Mapped[AttributeSource] = mapped_column(
        String(32), default=AttributeSource.SUBJECT, index=True
    )
    attribute_path: Mapped[str] = mapped_column(String(512), index=True)
    operator: Mapped[RuleOperator] = mapped_column(String(32), default=RuleOperator.EQUALS)
    comparison_value: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    """The expected value, wrapped in ``{"value": ...}``.

    Wrapped because a condition's value is legitimately any JSON type --
    a string, a number, a list of CIDRs -- and a bare JSON column
    holding a scalar is awkward to query and ambiguous to read back.
    """

    negate: Mapped[bool] = mapped_column(Boolean, default=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class PolicyAttribute(BaseModel):
    """``policy_attributes`` -- an attribute the estate knows how to supply.

    A catalogue, not a store of values: it declares that
    ``subject.department`` exists, what type it holds, and where it comes
    from. Policy authoring reads it so a UI can offer real attributes
    rather than a free-text box, and validation reads it to catch a
    policy referencing an attribute nothing will ever populate -- which
    otherwise evaluates as "missing" forever and silently never matches.
    """

    __tablename__ = "policy_attributes"
    __table_args__ = (
        UniqueConstraint("organization_id", "source", "path", name="uq_policy_attribute_path"),
    )

    source: Mapped[AttributeSource] = mapped_column(
        String(32), default=AttributeSource.SUBJECT, index=True
    )
    path: Mapped[str] = mapped_column(String(512), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, default=None)

    data_type: Mapped[str] = mapped_column(String(32), default="string")
    allowed_values: Mapped[list[Any]] = mapped_column(JSON, default=list)
    example_value: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    is_required: Mapped[bool] = mapped_column(Boolean, default=False)
    is_sensitive: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    """Whether the value must be redacted from stored traces.

    A decision trace records what each condition saw. For most
    attributes that is the point; for a few -- an authentication token,
    a personal identifier -- it would turn the decision log into a
    second copy of data that is protected elsewhere.
    """

    provided_by: Mapped[str | None] = mapped_column(String(128), default=None)
    """Which service supplies it, for the "attribute never populated" case."""


__all__ = ["PolicyAttribute", "PolicyCondition", "PolicyRule"]
