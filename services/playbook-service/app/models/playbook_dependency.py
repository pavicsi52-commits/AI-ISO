"""``playbook_dependencies`` table. Per docs/041 "DEPENDENCIES"
"Support": Playbook Dependencies, Role Dependencies, Collection
Dependencies, Python Packages, External Modules, Plugin Dependencies,
Circular Dependency Detection.
"""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import DependencyType


class PlaybookDependency(BaseModel):
    """One dependency a playbook requires to run."""

    __tablename__ = "playbook_dependencies"

    playbook_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("playbooks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dependency_type: Mapped[DependencyType] = mapped_column(String(24), index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    version_constraint: Mapped[str | None] = mapped_column(String(64), default=None)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)


__all__ = ["PlaybookDependency"]
