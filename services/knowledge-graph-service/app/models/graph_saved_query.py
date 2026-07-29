"""``graph_saved_queries`` table -- a reusable, parameterised query."""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import QueryKind


class GraphSavedQuery(BaseModel):
    """One saved query ("Saved Queries", "Parameterized Queries").

    ``parameter_schema`` declares the parameters a caller must bind. It
    is what lets a saved query stay parameterised through storage: the
    execution path binds the values against this declaration rather than
    substituting them into the text, so a saved query is not a
    stored-procedure-shaped injection hole.
    """

    __tablename__ = "graph_saved_queries"
    __table_args__ = (
        UniqueConstraint("organization_id", "slug", name="uq_graph_saved_query_slug"),
    )

    slug: Mapped[str] = mapped_column(String(128), index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    kind: Mapped[QueryKind] = mapped_column(String(32), default=QueryKind.CUSTOM_CYPHER, index=True)
    cypher: Mapped[str] = mapped_column(Text)
    parameter_schema: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    default_parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    execution_count: Mapped[int] = mapped_column(Integer, default=0)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(default=None, index=True)


__all__ = ["GraphSavedQuery"]
