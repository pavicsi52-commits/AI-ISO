"""``user_notes`` table.

Internal, admin/manager-authored notes about a user -- e.g. HR or
support annotations. Not user-facing (never returned by
``GET /users/{id}`` to the subject themselves); listed in docs/031's
"DATABASE TABLES" but not elaborated in a dedicated section, so this
follows the same minimal, auditable shape as every other entity here.
"""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column


class UserNote(BaseModel):
    """One internal note attached to a user."""

    __tablename__ = "user_notes"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)


__all__ = ["UserNote"]
