"""``secret_vault`` table -- the secret root entity.

Per docs/035 "SECRET MODEL": Secret ID, Organization ID, Project ID,
Name, Description, Category, Secret Type, Encrypted Value, Version,
Status, Owner, Expiration, Rotation Policy, Created At, Updated At,
Metadata, Tags.

**Zero plaintext persistence**: this table never stores a secret's
actual value, encrypted or otherwise -- only its identity, lifecycle,
and current version pointer. The "Encrypted Value" docs/035 names as a
model field is what :class:`~app.models.secret_version.SecretVersion`
carries (one row per version, each independently encrypted), and
``current_version`` here is a plain integer counter rather than a
foreign key to a specific version row -- avoiding a circular FK
(a version row must reference an already-existing secret, so the
secret can't simultaneously hold a not-yet-created version's id).

Unlike every other AI-IOS service's own ``project_id`` (inherited,
always ``None``), this entity's ``project_id`` is genuinely used --
docs/035's own "SECRET MODEL" names it as a real field, since a secret
can belong to a specific project rather than only its organization.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import SecretStatus, SecretType


class Secret(BaseModel):
    """One managed secret's identity and lifecycle -- never its value."""

    __tablename__ = "secret_vault"

    name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(String(2048), default=None)
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("secret_categories.id", ondelete="SET NULL"), default=None
    )
    secret_type: Mapped[SecretType] = mapped_column(String(32), index=True)
    status: Mapped[SecretStatus] = mapped_column(
        String(24), default=SecretStatus.ACTIVE, index=True
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(index=True)
    current_version: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    rotation_policy: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)


__all__ = ["Secret"]
