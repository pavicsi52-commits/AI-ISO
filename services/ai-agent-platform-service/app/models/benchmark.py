"""``agent_benchmarks``."""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import BenchmarkStatus


class AgentBenchmark(BaseModel):
    """``agent_benchmarks`` -- one regression-test-style benchmark suite
    run against an agent: a fixed set of cases, each scored, rolled up
    into a pass/fail count and an overall score.
    """

    __tablename__ = "agent_benchmarks"
    __table_args__ = (Index("ix_agent_benchmark_status", "status"),)

    agent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(128))
    status: Mapped[BenchmarkStatus] = mapped_column(
        String(16), default=BenchmarkStatus.PENDING, index=True
    )
    total_cases: Mapped[int] = mapped_column(Integer, default=0)
    passed_cases: Mapped[int] = mapped_column(Integer, default=0)
    failed_cases: Mapped[int] = mapped_column(Integer, default=0)
    score: Mapped[float | None] = mapped_column(Float, default=None)
    results: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    triggered_by: Mapped[str | None] = mapped_column(String(128), default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)


__all__ = ["AgentBenchmark"]
