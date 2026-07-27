"""``playbook_variables`` table. Per docs/041 "VARIABLES" "Support":
Defaults, Required Variables, Runtime Variables, Secrets References,
Environment Variables, Validation Rules, Variable Documentation.
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column


class PlaybookVariable(BaseModel):
    """One input-variable definition for a playbook."""

    __tablename__ = "playbook_variables"

    playbook_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("playbooks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), index=True)
    default_value: Mapped[str | None] = mapped_column(String(2048), default=None)
    required: Mapped[bool] = mapped_column(Boolean, default=False)
    runtime: Mapped[bool] = mapped_column(Boolean, default=False)
    is_secret_reference: Mapped[bool] = mapped_column(Boolean, default=False)
    env_var_name: Mapped[str | None] = mapped_column(String(255), default=None)
    validation_rule: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    description: Mapped[str | None] = mapped_column(Text, default=None)


__all__ = ["PlaybookVariable"]
