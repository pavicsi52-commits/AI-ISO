"""``graph_reports`` table -- a stored analysis result."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import AnalyticsAlgorithm, QueryKind


class GraphReport(BaseModel):
    """One stored analysis (impact, blast radius, or an analytics run).

    Impact and blast-radius analyses are expensive and are usually
    quoted in an incident review hours later. Storing the result -- with
    the parameters that produced it -- means the number in the review is
    the number the tool produced, not one someone re-derived against a
    graph that has since changed.
    """

    __tablename__ = "graph_reports"

    title: Mapped[str] = mapped_column(String(255), index=True)
    kind: Mapped[QueryKind] = mapped_column(String(32), index=True)
    algorithm: Mapped[AnalyticsAlgorithm | None] = mapped_column(
        String(32), default=None, index=True
    )
    root_key: Mapped[str | None] = mapped_column(String(255), default=None, index=True)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    summary: Mapped[str | None] = mapped_column(Text, default=None)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    affected_count: Mapped[int] = mapped_column(Integer, default=0)
    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    duration_ms: Mapped[float | None] = mapped_column(Float, default=None)
    generated_by: Mapped[uuid.UUID | None] = mapped_column(default=None, index=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


__all__ = ["GraphReport"]
