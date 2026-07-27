"""``validation_exceptions`` table -- a requested, reviewable waiver for
one known :class:`~app.models.validation_failure.ValidationFailure`
(e.g. an accepted-risk security finding a security team has
consciously decided not to fix yet). A separate approval workflow from
``validation_failures.is_resolved`` -- resolving a failure means it was
actually fixed; an exception means it was consciously *not* fixed but
should stop counting against scoring/alerting until ``expires_at``.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ValidationExceptionStatus


class ValidationException(BaseModel):
    """A requested, reviewable waiver for one known validation failure."""

    __tablename__ = "validation_exceptions"

    failure_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("validation_failures.id", ondelete="CASCADE"), index=True
    )
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[ValidationExceptionStatus] = mapped_column(
        String(16), default=ValidationExceptionStatus.PENDING, index=True
    )
    requested_by: Mapped[uuid.UUID] = mapped_column()
    decided_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    decision_reason: Mapped[str | None] = mapped_column(Text, default=None)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["ValidationException"]
