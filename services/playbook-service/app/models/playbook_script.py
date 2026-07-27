"""``playbook_scripts`` table -- auxiliary content files bundled
alongside a playbook's own :attr:`~app.models.playbook.Playbook
.entry_file`, per docs/041 "SUPPORTED CONTENT" (Python/PowerShell/
Shell/Bash Scripts).
"""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ContentType


class PlaybookScript(BaseModel):
    """One auxiliary content file bundled with a playbook."""

    __tablename__ = "playbook_scripts"

    playbook_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("playbooks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_name: Mapped[str] = mapped_column(String(255))
    script_type: Mapped[ContentType] = mapped_column(String(32), index=True)
    content: Mapped[str] = mapped_column(Text)
    is_entry_point: Mapped[bool] = mapped_column(Boolean, default=False)


__all__ = ["PlaybookScript"]
