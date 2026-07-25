"""``secret_categories`` table -- a simple, per-organization taxonomy for
secrets, referenced by :attr:`~app.models.secret.Secret.category_id`.
"""

from __future__ import annotations

from shared_core.database.base import BaseModel
from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class SecretCategory(BaseModel):
    """One organization-scoped secret category."""

    __tablename__ = "secret_categories"
    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_secret_category_name"),)

    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(String(1024), default=None)


__all__ = ["SecretCategory"]
