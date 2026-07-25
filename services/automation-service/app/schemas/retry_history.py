"""Response schema for an automation execution's own retry history."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import FailureClassification, RetryStrategy


class AutomationRetryHistoryResponse(BaseModel):
    """One retry attempt recorded against an execution (or one of its steps)."""

    id: UUID
    execution_id: UUID
    step_id: UUID | None
    attempt_number: int
    strategy: RetryStrategy
    classification: FailureClassification | None
    succeeded: bool
    attempted_at: datetime


__all__ = ["AutomationRetryHistoryResponse"]
