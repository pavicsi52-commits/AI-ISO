"""``prompt_templates``, ``prompt_variables``, ``prompt_categories``,
and ``prompt_tags``.
"""

from __future__ import annotations

import uuid

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

from app.models.enums import PromptCategory, TemplateFormat, VariableKind, VariableType


class PromptTemplate(BaseModel):
    """``prompt_templates`` -- one reusable, composable template body.

    Covers docs/061's own "TEMPLATE MANAGEMENT" section: a template can
    ``extends`` a parent (Inheritance), ``include`` others
    (Composition/Nested Templates/Shared Components), declare its own
    variables, and exist per ``locale`` (Localization). Conditional
    Sections need no column at all -- they are Jinja2 ``{% if %}``
    blocks inside ``body``, which is exactly why rendering goes through
    a sandboxed Jinja2 environment rather than string substitution.
    """

    __tablename__ = "prompt_templates"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "slug", "locale", name="uq_prompt_template_slug_locale"
        ),
        Index("ix_prompt_template_slug", "slug"),
    )

    slug: Mapped[str] = mapped_column(String(128), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    body: Mapped[str] = mapped_column(Text)
    template_format: Mapped[TemplateFormat] = mapped_column(
        String(16), default=TemplateFormat.PLAIN_TEXT
    )
    locale: Mapped[str] = mapped_column(String(16), default="en")
    """ "TEMPLATE MANAGEMENT": Localization. Part of the natural key
    alongside ``slug``, so the same template in two languages is two
    rows rather than one row with a language column nobody filters on."""
    parent_template_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("prompt_templates.id", ondelete="SET NULL"), default=None, index=True
    )
    """ "Inheritance". Self-referential and nullable; cycle detection is
    the renderer's job, since a cycle is only detectable across the
    whole chain, not at insert time for one row."""
    included_template_slugs: Mapped[list[str]] = mapped_column(JSON, default=list)
    """ "Composition"/"Shared Components" -- resolved by slug at render
    time rather than by foreign key, so a template can reference a
    shared component that is versioned independently of it."""
    is_shared_component: Mapped[bool] = mapped_column(Boolean, default=False)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)


class PromptVariable(BaseModel):
    """``prompt_variables`` -- one declared input to a prompt or template.

    Declared per prompt *version*, not per prompt: a revision that
    introduces a new variable must not retroactively change what an
    already-approved revision requires.

    **A ``SECRET_REFERENCE`` variable never stores its value here.**
    ``secret_reference`` holds the lookup key resolved live against
    secrets-management-service at render time, so a secret's plaintext
    has no path into this table, into a backup of it, or into a
    rendered prompt that later gets logged.
    """

    __tablename__ = "prompt_variables"
    __table_args__ = (
        UniqueConstraint("prompt_version_id", "name", name="uq_prompt_variable_name"),
        Index("ix_prompt_variable_kind", "kind"),
    )

    prompt_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("prompt_versions.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    kind: Mapped[VariableKind] = mapped_column(String(24), default=VariableKind.STATIC, index=True)
    value_type: Mapped[VariableType] = mapped_column(String(16), default=VariableType.STRING)
    default_value: Mapped[str | None] = mapped_column(Text, default=None)
    required: Mapped[bool] = mapped_column(Boolean, default=True)
    secret_reference: Mapped[str | None] = mapped_column(String(255), default=None)
    computed_expression: Mapped[str | None] = mapped_column(Text, default=None)
    """ "Computed Variables" -- a sandboxed Jinja2 expression evaluated
    against the other resolved variables."""
    validation_rules: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    """ "Validation Rules" -- min/max, pattern, enum, min_length,
    max_length. Enforced by ``app/variables/validation.py``."""
    is_masked: Mapped[bool] = mapped_column(Boolean, default=False)
    """ "Sensitive Data Masking" -- this value is redacted out of
    execution history and audit rows even when it is not a secret
    reference."""


class PromptCategoryRecord(BaseModel):
    """``prompt_categories`` -- one organization-curated category.

    Named ``PromptCategoryRecord`` rather than ``PromptCategory`` to
    avoid colliding with the platform's own fixed
    :class:`~app.models.enums.PromptCategory` taxonomy, which these
    rows reference. The two are complementary, not redundant: the enum
    is the closed vocabulary this service ships with, this table is the
    open set a tenant curates on top of it.
    """

    __tablename__ = "prompt_categories"
    __table_args__ = (UniqueConstraint("organization_id", "slug", name="uq_prompt_category_slug"),)

    slug: Mapped[str] = mapped_column(String(128), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    base_category: Mapped[PromptCategory] = mapped_column(String(32), default=PromptCategory.CUSTOM)
    owner_id: Mapped[str | None] = mapped_column(String(128), default=None)
    prompt_count: Mapped[int] = mapped_column(Integer, default=0)


class PromptTag(BaseModel):
    """``prompt_tags`` -- one tag applied to one prompt.

    A join row rather than a JSON array on ``prompts`` even though
    ``Prompt.tags`` exists: that column is the fast denormalized copy
    for rendering a prompt, while these rows are what make
    "every prompt tagged X, across the organization" a real indexed
    query instead of a JSON scan.
    """

    __tablename__ = "prompt_tags"
    __table_args__ = (
        UniqueConstraint("prompt_id", "tag", name="uq_prompt_tag"),
        Index("ix_prompt_tag_tag", "tag"),
    )

    prompt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("prompts.id", ondelete="CASCADE"), index=True
    )
    tag: Mapped[str] = mapped_column(String(64), index=True)
    applied_by: Mapped[str | None] = mapped_column(String(128), default=None)


__all__ = ["PromptCategoryRecord", "PromptTag", "PromptTemplate", "PromptVariable"]
