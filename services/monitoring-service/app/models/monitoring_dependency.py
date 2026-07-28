"""``monitoring_dependencies`` table -- one edge in the dependency graph
("DEPENDENCY HEALTH" "Support": Topology-aware Health, Parent/Child
Health, Blast Radius Calculation). ``parent_target_id`` is the
depended-*upon* target (e.g. a database); ``child_target_id`` is the
target that depends on it (e.g. an application) -- when the parent's
own health degrades, walking every row with that ``parent_target_id``
gives the blast radius of targets whose own health may be affected.
"""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import DependencyType


class MonitoringDependency(BaseModel):
    """One edge in the target dependency graph."""

    __tablename__ = "monitoring_dependencies"

    parent_target_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("monitoring_targets.id", ondelete="CASCADE"), index=True
    )
    child_target_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("monitoring_targets.id", ondelete="CASCADE"), index=True
    )
    dependency_type: Mapped[DependencyType] = mapped_column(String(16), index=True)


__all__ = ["MonitoringDependency"]
