"""``automation_parameters`` table -- the typed input-parameter
definitions a job's own ``content`` expects at execution time,
distinct from :class:`~app.models.automation_variable.AutomationVariable`'s
own reusable, cross-job scoped values.
"""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column


class AutomationParameter(BaseModel):
    """One input-parameter definition for an automation job."""

    __tablename__ = "automation_parameters"

    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("automation_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), index=True)
    parameter_type: Mapped[str] = mapped_column(String(32), default="string")
    required: Mapped[bool] = mapped_column(Boolean, default=False)
    default_value: Mapped[str | None] = mapped_column(String(2048), default=None)
    description: Mapped[str | None] = mapped_column(String(1024), default=None)


__all__ = ["AutomationParameter"]
