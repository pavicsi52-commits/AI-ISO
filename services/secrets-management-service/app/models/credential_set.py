"""``credential_sets`` table -- a named bundle of related secrets (e.g. a
service account's private key plus its associated password), grouped
for retrieval as one logical credential rather than a single secret
type on its own.
"""

from __future__ import annotations

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column


class CredentialSet(BaseModel):
    """One named bundle of related secret ids."""

    __tablename__ = "credential_sets"

    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(String(2048), default=None)
    secret_ids: Mapped[list[str]] = mapped_column(JSON, default=list)


__all__ = ["CredentialSet"]
