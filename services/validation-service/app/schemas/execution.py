"""Request/response schemas for ``POST /validations/{id}/execute``.

Not literally named as its own resource anywhere in docs/043's own REST
APIs list (only ``execute``/``cancel`` *actions* on ``/validations``
are) -- ``ValidationExecutionResponse`` is added directly, the same
"required capability with no REST list entry" precedent every prior
AI-IOS service has established at least once, since the response of
``execute`` (and the executions list this service tracks internally)
must be shaped somehow.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import (
    ValidationConcurrencyStrategy,
    ValidationExecutionStatus,
    ValidationTriggerType,
)
from app.schemas.target import TargetReference


class ValidationExecuteRequest(BaseModel):
    """Body of ``POST /validations/{id}/execute``."""

    targets: list[TargetReference] = Field(min_length=1)
    concurrency_strategy: ValidationConcurrencyStrategy | None = None


class ValidationExecutionResponse(BaseModel):
    """One run of a validation profile against one or more targets."""

    id: UUID
    organization_id: UUID
    project_id: UUID | None
    profile_id: UUID
    target_ids: list[str]
    trigger_type: ValidationTriggerType
    concurrency_strategy: ValidationConcurrencyStrategy
    status: ValidationExecutionStatus
    triggered_by: UUID | None
    started_at: datetime | None
    finished_at: datetime | None
    error_message: str | None


__all__ = ["ValidationExecuteRequest", "ValidationExecutionResponse"]
