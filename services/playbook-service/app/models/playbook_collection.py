"""``playbook_collections`` table -- Ansible collection references a
playbook depends on, per docs/041 "SUPPORTED CONTENT" "Ansible
Collections".
"""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column


class PlaybookCollection(BaseModel):
    """One Ansible collection a playbook references."""

    __tablename__ = "playbook_collections"

    playbook_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("playbooks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    collection_name: Mapped[str] = mapped_column(String(255), index=True)
    collection_version: Mapped[str | None] = mapped_column(String(64), default=None)
    source: Mapped[str | None] = mapped_column(String(255), default=None)


__all__ = ["PlaybookCollection"]
