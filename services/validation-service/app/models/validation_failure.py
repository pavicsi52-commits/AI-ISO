"""``validation_failures`` table -- a durable, trackable record that one
:class:`~app.models.validation_result.ValidationResult` failed,
separate from the result itself so a failure can carry its own
resolution lifecycle (``is_resolved``/``resolved_at``) independent of
the immutable result row that produced it, and so
:class:`~app.models.validation_exception.ValidationException` and
:class:`~app.models.validation_remediation.ValidationRemediation` have
a stable row to reference.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ValidationSeverity


class ValidationFailure(BaseModel):
    """A durable, trackable record that one validation result failed."""

    __tablename__ = "validation_failures"

    result_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("validation_results.id", ondelete="CASCADE"), index=True
    )
    severity: Mapped[ValidationSeverity] = mapped_column(
        String(16), default=ValidationSeverity.MEDIUM, index=True
    )
    reason: Mapped[str] = mapped_column(Text)
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(default=None)


__all__ = ["ValidationFailure"]
