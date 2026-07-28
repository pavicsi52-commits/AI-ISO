"""``report_parameters`` table -- one declared input of a report."""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ParameterKind


class ReportParameter(BaseModel):
    """One parameter a template declares.

    Declared per *template*, not per job: the template is what knows
    which inputs its sections reference, and a job simply supplies
    values for them.
    """

    __tablename__ = "report_parameters"
    __table_args__ = (
        UniqueConstraint("template_id", "key", name="uq_report_parameter_template_key"),
    )

    template_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("report_templates.id", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(String(64), index=True)
    label: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    kind: Mapped[ParameterKind] = mapped_column(String(16))
    required: Mapped[bool] = mapped_column(Boolean, default=False)
    default_value: Mapped[Any | None] = mapped_column(JSON, default=None)
    allowed_values: Mapped[list[Any]] = mapped_column(JSON, default=list)
    display_order: Mapped[int] = mapped_column(default=0)


__all__ = ["ReportParameter"]
