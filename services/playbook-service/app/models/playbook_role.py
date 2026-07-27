"""``playbook_roles`` table -- Ansible role references a playbook
depends on, per docs/041 "SUPPORTED CONTENT" "Ansible Roles".
"""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column


class PlaybookRole(BaseModel):
    """One Ansible role a playbook references."""

    __tablename__ = "playbook_roles"

    playbook_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("playbooks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role_name: Mapped[str] = mapped_column(String(255), index=True)
    role_source: Mapped[str] = mapped_column(String(32), default="galaxy")
    role_version: Mapped[str | None] = mapped_column(String(64), default=None)


__all__ = ["PlaybookRole"]
