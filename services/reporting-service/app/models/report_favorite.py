"""``report_favorites`` table -- a user's own pinned reports."""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class ReportFavorite(BaseModel):
    """One user's favourite report.

    The unique constraint is on ``(user_id, job_id)``, so favouriting
    twice is idempotent at the database level rather than relying on
    every caller to check first.
    """

    __tablename__ = "report_favorites"
    __table_args__ = (UniqueConstraint("user_id", "job_id", name="uq_report_favorite_user_job"),)

    user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("report_jobs.id", ondelete="CASCADE"), index=True
    )


__all__ = ["ReportFavorite"]
