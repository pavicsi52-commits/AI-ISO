"""``prompts`` and ``prompt_versions``.

The identity/revision split is the spine of this whole service: a
:class:`Prompt` is a stable, referenceable identity, and its actual
text lives only in immutable :class:`PromptVersion` rows. That is what
makes versioning, approval, rollback, and comparison real rather than
nominal -- an approved revision's text can never be edited in place, so
"this is the wording that was approved" stays true forever.

Mirrors the same split ``ai-assistant-service``'s own smaller
``AiPrompt``/``AiPromptVersion`` pair (Prompt 046) established, scaled
up to this service's own full governance surface.
"""

from __future__ import annotations

import uuid
from datetime import datetime

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

from app.models.enums import (
    PromptCategory,
    PromptLifecycleStatus,
    PromptType,
    PromptVersionStatus,
    SharingScope,
    TemplateFormat,
)


class Prompt(BaseModel):
    """``prompts`` -- one addressable prompt identity.

    Carries no prompt text of its own. ``current_version_number``
    points at whichever :class:`PromptVersion` is live; retrieval
    resolves through it, so publishing a new revision or rolling back
    to an older one is a single pointer move rather than a rewrite.
    """

    __tablename__ = "prompts"
    __table_args__ = (
        UniqueConstraint("organization_id", "slug", name="uq_prompt_slug"),
        Index("ix_prompt_type", "prompt_type"),
        Index("ix_prompt_status", "status"),
        Index("ix_prompt_category", "category"),
    )

    slug: Mapped[str] = mapped_column(String(128), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    prompt_type: Mapped[PromptType] = mapped_column(String(24), index=True)
    category: Mapped[PromptCategory] = mapped_column(
        String(32), default=PromptCategory.CUSTOM, index=True
    )
    status: Mapped[PromptLifecycleStatus] = mapped_column(
        String(16), default=PromptLifecycleStatus.DRAFT, index=True
    )
    sharing_scope: Mapped[SharingScope] = mapped_column(String(16), default=SharingScope.PRIVATE)
    current_version_number: Mapped[str | None] = mapped_column(String(32), default=None)
    """The live revision's own semantic version -- never ``version``,
    which ``BaseEntityMixin`` already reserves for optimistic locking."""
    owner_id: Mapped[str | None] = mapped_column(String(128), default=None)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    forked_from_prompt_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("prompts.id", ondelete="SET NULL"), default=None, index=True
    )
    """Set by "Fork"/"Clone". Nullable and ``SET NULL`` on delete: a
    fork must outlive the prompt it came from, since the whole point is
    that it is now independently owned."""
    execution_count: Mapped[int] = mapped_column(Integer, default=0)
    last_executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    """Backs the review-cycle sweep ("GOVERNANCE": Review Cycle)."""
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    """ "GOVERNANCE": Expiration Policies -- a prompt that must be
    re-certified by a date rather than left live indefinitely."""


class PromptVersion(BaseModel):
    """``prompt_versions`` -- one immutable revision of a prompt's text.

    ``version_number``, not ``version`` -- the same reserved-column
    collision this build has hit and fixed repeatedly since Prompt 033.
    """

    __tablename__ = "prompt_versions"
    __table_args__ = (
        UniqueConstraint("prompt_id", "version_number", name="uq_prompt_version_number"),
        Index("ix_prompt_version_status", "status"),
    )

    prompt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("prompts.id", ondelete="CASCADE"), index=True
    )
    version_number: Mapped[str] = mapped_column(String(32))
    status: Mapped[PromptVersionStatus] = mapped_column(
        String(16), default=PromptVersionStatus.DRAFT, index=True
    )
    body: Mapped[str] = mapped_column(Text)
    """The prompt text itself, as a template. Immutable once
    ``PUBLISHED``."""
    template_format: Mapped[TemplateFormat] = mapped_column(
        String(16), default=TemplateFormat.PLAIN_TEXT
    )
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("prompt_templates.id", ondelete="SET NULL"), default=None, index=True
    )
    """The reusable template this revision extends, if any
    ("TEMPLATE MANAGEMENT": Inheritance)."""
    changelog: Mapped[str | None] = mapped_column(Text, default=None)
    model_hint: Mapped[str | None] = mapped_column(String(128), default=None)
    """Which model this wording was tuned for, recorded so an
    evaluation run against a different model is comparable knowingly
    rather than accidentally."""
    estimated_tokens: Mapped[int] = mapped_column(Integer, default=0)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    published_by: Mapped[str | None] = mapped_column(String(128), default=None)
    created_by: Mapped[str | None] = mapped_column(String(128), default=None)
    average_score: Mapped[float | None] = mapped_column(Float, default=None)
    """Rolled up from this revision's own evaluations, so comparing two
    versions does not require re-reading every evaluation row."""


__all__ = ["Prompt", "PromptVersion"]
