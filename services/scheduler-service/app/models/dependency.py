"""``job_dependencies`` -- how one job's execution depends on another's.

Directional: *child* depends on *parent* per *dependency_type* -- the
inverse is not stored as its own row, the same reasoning
``services/change-management-service``'s ``ChangeRelationship`` applies.
"""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import DependencyCondition, DependencyType


class JobDependency(BaseModel):
    """``job_dependencies`` -- *child_job* depends on *parent_job*."""

    __tablename__ = "job_dependencies"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "parent_job_id", "child_job_id", name="uq_job_dependency_edge"
        ),
        Index("ix_job_dependency_parent", "organization_id", "parent_job_id"),
        Index("ix_job_dependency_child", "organization_id", "child_job_id"),
    )

    parent_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scheduled_jobs.id", ondelete="CASCADE"), index=True
    )
    child_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scheduled_jobs.id", ondelete="CASCADE"), index=True
    )
    dependency_type: Mapped[DependencyType] = mapped_column(
        String(32), default=DependencyType.SEQUENTIAL
    )
    condition: Mapped[DependencyCondition | None] = mapped_column(String(32), default=None)
    """Only meaningful -- and only ever set -- for ``CONDITIONAL``
    dependencies; ``SEQUENTIAL``/``PARALLEL`` edges leave it ``None``."""


__all__ = ["JobDependency"]
