"""``graph_statistics`` table -- one analytics rollup per organization."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column


class GraphStatistics(BaseModel):
    """An organization graph statistics rollup.

    One row per organization, updated in place and always **derived**
    from the graph rather than incremented. A counter bumped on every
    node write drifts the moment one write is lost, and nothing can tell
    you that it has.
    """

    __tablename__ = "graph_statistics"

    node_count: Mapped[int] = mapped_column(Integer, default=0)
    relationship_count: Mapped[int] = mapped_column(Integer, default=0)
    node_type_counts: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    relationship_type_counts: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    orphan_count: Mapped[int] = mapped_column(Integer, default=0)
    """Nodes with no relationships at all.

    Almost always a synchronization bug rather than a real fact about
    the estate, which is why it gets its own figure instead of hiding
    inside the node count.
    """

    average_degree: Mapped[float] = mapped_column(Float, default=0.0)
    max_degree: Mapped[int] = mapped_column(Integer, default=0)
    density: Mapped[float] = mapped_column(Float, default=0.0)
    connected_components: Mapped[int] = mapped_column(Integer, default=0)
    critical_assets: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    twin_counts: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    sync_health: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


__all__ = ["GraphStatistics"]
