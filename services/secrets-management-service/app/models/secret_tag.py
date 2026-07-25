"""``secret_tags`` table -- free-form tags on a secret, mirroring every
prior AI-IOS service's identical tag shape. Per docs/035 "SECRET
SEARCH": "Tags".
"""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class SecretTag(BaseModel):
    """One tag assigned to a secret."""

    __tablename__ = "secret_tags"
    __table_args__ = (UniqueConstraint("secret_id", "label", name="uq_secret_tag_label"),)

    secret_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("secret_vault.id", ondelete="CASCADE"), nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(String(128))


__all__ = ["SecretTag"]
