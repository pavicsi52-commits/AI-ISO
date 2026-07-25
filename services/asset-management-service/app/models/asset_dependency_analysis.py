"""``asset_dependency_analysis`` table. Per docs/038 "DEPENDENCY
ANALYSIS": Integrate with Neo4j; Support Impact Analysis, Dependency
Graph, Service/Application/Infrastructure Dependency, Blast Radius
Analysis, Root Cause Relationships. Neo4j (already populated by
``inventory-service``'s own topology graph, keyed by
``ManagedAsset.inventory_asset_id``) is queried live for graph
traversal; this table is a cached rollup of the *last computed*
analysis, matching PERFORMANCE's own "Caching"/"Neo4j Query
Optimization" requirement rather than re-traversing the graph on every
read.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class AssetDependencyAnalysis(BaseModel):
    """One managed asset's cached dependency-graph analysis."""

    __tablename__ = "asset_dependency_analysis"
    __table_args__ = (
        UniqueConstraint("managed_asset_id", name="uq_asset_dependency_analysis_managed_asset"),
    )

    managed_asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("managed_assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dependency_count: Mapped[int] = mapped_column(Integer, default=0)
    dependent_count: Mapped[int] = mapped_column(Integer, default=0)
    blast_radius_count: Mapped[int] = mapped_column(Integer, default=0)
    graph_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


__all__ = ["AssetDependencyAnalysis"]
