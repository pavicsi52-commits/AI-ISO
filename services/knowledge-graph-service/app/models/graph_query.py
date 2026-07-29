"""``graph_queries`` table -- the record of one executed query."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import QueryKind


class GraphQuery(BaseModel):
    """One executed graph query ("GRAPH QUERIES", "AUDIT").

    Recorded per execution so a slow traversal can be traced back to the
    caller and the parameters that produced it. ``cypher`` is stored
    with its parameters *separate* -- the same discipline the execution
    path enforces, and it means a recorded query can never be replayed
    as a concatenated string.
    """

    __tablename__ = "graph_queries"

    kind: Mapped[QueryKind] = mapped_column(String(32), index=True)
    cypher: Mapped[str] = mapped_column(Text)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    saved_query_id: Mapped[uuid.UUID | None] = mapped_column(default=None, index=True)
    succeeded: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    truncated: Mapped[bool] = mapped_column(Boolean, default=False)
    duration_ms: Mapped[float | None] = mapped_column(Float, default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    executed_by: Mapped[uuid.UUID | None] = mapped_column(default=None, index=True)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


__all__ = ["GraphQuery"]
