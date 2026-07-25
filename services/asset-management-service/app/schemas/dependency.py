"""Response schemas for ``GET /assets/{id}/dependencies``."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class DependencyGraphNode(BaseModel):
    """One node returned by a dependency-graph traversal."""

    id: str
    name: str | None
    asset_type: str | None
    distance: int


class AssetDependencyResponse(BaseModel):
    """A managed asset's full dependency analysis -- per docs/038
    "DEPENDENCY ANALYSIS": Impact Analysis, Dependency Graph, Blast
    Radius Analysis, Root Cause Relationships.
    """

    managed_asset_id: UUID
    inventory_asset_id: UUID
    dependency_graph: list[DependencyGraphNode]
    impact_analysis: list[DependencyGraphNode]
    blast_radius: list[DependencyGraphNode]
    root_cause_candidates: list[DependencyGraphNode]
    computed_at: datetime


__all__ = ["AssetDependencyResponse", "DependencyGraphNode"]
