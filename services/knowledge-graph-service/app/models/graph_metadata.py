"""``graph_metadata`` table -- per-node metadata the graph itself should not carry."""

from __future__ import annotations

from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, Float, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import LifecycleState, TwinType


class GraphMetadata(BaseModel):
    """Metadata about one graph node ("DIGITAL TWIN", "Bidirectional Metadata Sync").

    Node identity and relationships live in Neo4j; everything an
    operator *annotates* lives here. Two reasons, both practical: this
    is the mutable, frequently-written side, and keeping it in Postgres
    keeps write pressure off the graph a traversal is reading; and it is
    the side with real uniqueness and referential constraints, which
    Neo4j expresses far less naturally.

    ``node_key`` is the join. It is the same stable business key the
    graph stores as ``key`` on the node, not a Neo4j internal id --
    internal ids are reused after deletion and are explicitly not stable
    across restores.
    """

    __tablename__ = "graph_metadata"
    __table_args__ = (
        UniqueConstraint("organization_id", "node_key", name="uq_graph_metadata_node"),
    )

    node_key: Mapped[str] = mapped_column(String(255), index=True)
    node_type: Mapped[str] = mapped_column(String(64), index=True)
    display_name: Mapped[str | None] = mapped_column(String(255), default=None)
    twin_type: Mapped[TwinType | None] = mapped_column(String(24), default=None, index=True)
    lifecycle_state: Mapped[LifecycleState] = mapped_column(
        String(16), default=LifecycleState.ACTIVE, index=True
    )
    health_status: Mapped[str | None] = mapped_column(String(16), default=None, index=True)
    criticality: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    """Operator-declared importance, 0.0-1.0.

    Distinct from computed centrality: a node can be structurally
    peripheral and still be the one thing the business cannot lose.
    Risk propagation uses both.
    """

    owner_team: Mapped[str | None] = mapped_column(String(255), default=None, index=True)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    """Excluded from synchronization deletes.

    A node someone deliberately added by hand must not vanish because a
    source service has never heard of it.
    """


__all__ = ["GraphMetadata"]
