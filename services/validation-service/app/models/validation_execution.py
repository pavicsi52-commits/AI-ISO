"""``validation_executions`` table -- one run of a
:class:`~app.models.validation_profile.ValidationProfile` against one
or more :class:`~app.models.validation_target.ValidationTarget` rows.

``target_ids`` is a JSON array of target row ids (as strings, the same
"json can't serialize a raw UUID" reasoning
``ValidationProfile.check_ids`` already documents) rather than a join
table, since docs/043's own 17-table list has no
``validation_execution_targets`` table either.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import (
    ValidationConcurrencyStrategy,
    ValidationExecutionStatus,
    ValidationTriggerType,
)


class ValidationExecution(BaseModel):
    """One run of a validation profile against one or more targets."""

    __tablename__ = "validation_executions"

    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("validation_profiles.id", ondelete="CASCADE"), index=True
    )
    target_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    trigger_type: Mapped[ValidationTriggerType] = mapped_column(
        String(24), default=ValidationTriggerType.MANUAL
    )
    concurrency_strategy: Mapped[ValidationConcurrencyStrategy] = mapped_column(
        String(16), default=ValidationConcurrencyStrategy.SEQUENTIAL
    )
    status: Mapped[ValidationExecutionStatus] = mapped_column(
        String(16), default=ValidationExecutionStatus.QUEUED, index=True
    )
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    error_message: Mapped[str | None] = mapped_column(Text, default=None)


__all__ = ["ValidationExecution"]
