"""``notification_templates`` and ``notification_template_versions``.

Docs/055 "TEMPLATE MANAGEMENT": "Template Versioning". Editing a
template's live copy in place would silently change the wording of
every notification already in flight against the old copy's promise;
:class:`NotificationTemplateVersion` keeps every prior body/subject
retrievable by its own version number, mirroring
`shared_core.notifications.templates.TemplateRegistry`'s own
``(template_id, locale, version)`` keying, persisted.
"""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import NotificationCategory, TemplateFormat


class NotificationTemplate(BaseModel):
    """``notification_templates`` -- one reusable, versioned, localized template."""

    __tablename__ = "notification_templates"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "template_key", "locale", name="uq_notification_template_key_locale"
        ),
    )

    template_key: Mapped[str] = mapped_column(String(128), index=True)
    """The logical key callers reference, e.g. ``"job.failed"`` --
    stable across every locale and version."""

    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    category: Mapped[NotificationCategory | None] = mapped_column(String(32), default=None)

    format: Mapped[TemplateFormat] = mapped_column(String(16), default=TemplateFormat.PLAIN_TEXT)
    locale: Mapped[str] = mapped_column(String(16), default="en")

    subject_template: Mapped[str | None] = mapped_column(Text, default=None)
    body_template: Mapped[str] = mapped_column(Text)

    current_version: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class NotificationTemplateVersion(BaseModel):
    """``notification_template_versions`` -- one immutable, retrievable prior version."""

    __tablename__ = "notification_template_versions"
    __table_args__ = (
        UniqueConstraint("template_id", "version", name="uq_notification_template_version"),
        Index("ix_notification_template_version_template", "organization_id", "template_id"),
    )

    template_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("notification_templates.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    subject_template: Mapped[str | None] = mapped_column(Text, default=None)
    body_template: Mapped[str] = mapped_column(Text)
    format: Mapped[TemplateFormat] = mapped_column(String(16), default=TemplateFormat.PLAIN_TEXT)
    change_note: Mapped[str | None] = mapped_column(Text, default=None)


__all__ = ["NotificationTemplate", "NotificationTemplateVersion"]
