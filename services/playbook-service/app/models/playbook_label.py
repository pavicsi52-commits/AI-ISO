"""``playbook_labels`` table -- one key/value label pair per playbook
per row, per docs/041 "PLAYBOOK MODEL" "Labels".
"""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class PlaybookLabel(BaseModel):
    """One key/value label assigned to a playbook."""

    __tablename__ = "playbook_labels"
    __table_args__ = (UniqueConstraint("playbook_id", "key", name="uq_playbook_label_key"),)

    playbook_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("playbooks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(String(100), index=True)
    value: Mapped[str] = mapped_column(String(512))


__all__ = ["PlaybookLabel"]
