"""``validation_remediation`` table -- one suggested or applied fix for
a :class:`~app.models.validation_failure.ValidationFailure`. Per
docs/043's own "REMEDIATION" "Support" list: the fields present
(``automation_job_key``, ``playbook_key``, ``workflow_key``,
``knowledge_base_url``) are all mutually optional -- which ones are
populated depends on ``action_type``. Applying an automation/playbook/
workflow suggestion is never done automatically by this service (see
``app/services/remediation.py``'s own docstring) -- ``is_applied`` only
ever reflects a caller's own explicit confirmation that they ran it
elsewhere.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import RemediationActionType


class ValidationRemediation(BaseModel):
    """One suggested or applied fix for a validation failure."""

    __tablename__ = "validation_remediation"

    failure_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("validation_failures.id", ondelete="CASCADE"), index=True
    )
    action_type: Mapped[RemediationActionType] = mapped_column(String(32), index=True)
    description: Mapped[str] = mapped_column(Text)
    automation_job_key: Mapped[str | None] = mapped_column(String(255), default=None)
    playbook_key: Mapped[str | None] = mapped_column(String(255), default=None)
    workflow_key: Mapped[str | None] = mapped_column(String(255), default=None)
    knowledge_base_url: Mapped[str | None] = mapped_column(String(2048), default=None)
    is_applied: Mapped[bool] = mapped_column(Boolean, default=False)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    applied_by: Mapped[uuid.UUID | None] = mapped_column(default=None)


__all__ = ["ValidationRemediation"]
