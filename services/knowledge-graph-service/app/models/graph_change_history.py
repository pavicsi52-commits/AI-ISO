"""``graph_change_history`` table -- what changed in the graph, and when."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ChangeAction


class GraphChangeHistory(BaseModel):
    """One recorded graph change ("Change Tracking").

    Kept in PostgreSQL rather than as extra nodes in Neo4j: a change log
    is an append-only time series, which is exactly what a relational
    table is good at and exactly what makes a graph slower to traverse.

    ``before``/``after`` hold the changed properties only, not whole
    nodes. A full copy of every node on every property change would make
    this table larger than the graph within a week.
    """

    __tablename__ = "graph_change_history"

    action: Mapped[ChangeAction] = mapped_column(String(32), index=True)
    node_key: Mapped[str | None] = mapped_column(String(255), default=None, index=True)
    relationship_key: Mapped[str | None] = mapped_column(String(255), default=None, index=True)
    entity_type: Mapped[str] = mapped_column(String(64), index=True)
    before: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    after: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    sync_job_id: Mapped[uuid.UUID | None] = mapped_column(default=None, index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(default=None, index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


__all__ = ["GraphChangeHistory"]
