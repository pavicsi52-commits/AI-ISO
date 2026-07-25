"""Response schema for ``GET /inventory/topology``. Per docs/036
"TOPOLOGY": Dependency Graph, Relationship Traversal, Impact Analysis.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class TopologyNode(BaseModel):
    """One asset reachable from the query's root asset."""

    id: UUID
    name: str
    asset_type: str
    distance: int | None = None
    relationship_type: str | None = None
    outgoing: bool | None = None


class TopologyResponse(BaseModel):
    """The result of one topology traversal query."""

    root_asset_id: UUID
    query_kind: str
    nodes: list[TopologyNode]


__all__ = ["TopologyNode", "TopologyResponse"]
