"""``playbooks`` table -- the reusable automation content definition.

Per docs/041 "PLAYBOOK MODEL": a playbook is metadata plus a pointer to
its own *current* :class:`~app.models.playbook_version.PlaybookVersion`
-- the actual content (script/YAML/template body) lives in that
version snapshot, never inline here, the same definition/content-
snapshot split ``services/configuration-management-service``'s own
``ConfigurationProfile``/``ConfigurationVersion`` pair established.

``current_version`` (a version *string*, e.g. ``"1.2.0"``) is
deliberately not named ``version`` -- that name is already
``BaseModel``'s own inherited optimistic-concurrency integer column;
naming around this collision proactively, the same precedent
``ConfigurationProfile.profile_version`` already established.
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ContentType, PlaybookStatus


class Playbook(BaseModel):
    """One reusable automation content definition."""

    __tablename__ = "playbooks"

    name: Mapped[str] = mapped_column(String(255), index=True)
    display_name: Mapped[str | None] = mapped_column(String(255), default=None)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    content_type: Mapped[ContentType] = mapped_column(String(32), index=True)
    status: Mapped[PlaybookStatus] = mapped_column(
        String(16), default=PlaybookStatus.DRAFT, index=True
    )
    current_version: Mapped[str | None] = mapped_column(String(32), default=None)
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("playbook_categories.id", ondelete="SET NULL"), default=None, index=True
    )
    repository_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("playbook_repository.id", ondelete="SET NULL"), default=None, index=True
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    author_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    entry_file: Mapped[str | None] = mapped_column(String(512), default=None)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)


__all__ = ["Playbook"]
