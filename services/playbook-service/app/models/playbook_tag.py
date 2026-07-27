"""``playbook_tags`` table -- one tag per playbook per row, per docs/041
"PLAYBOOK MODEL" "Tags".
"""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class PlaybookTag(BaseModel):
    """One tag assigned to a playbook."""

    __tablename__ = "playbook_tags"
    __table_args__ = (UniqueConstraint("playbook_id", "tag", name="uq_playbook_tag"),)

    playbook_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("playbooks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tag: Mapped[str] = mapped_column(String(100), index=True)


__all__ = ["PlaybookTag"]
