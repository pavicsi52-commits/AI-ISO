"""Validation result response payload."""

from __future__ import annotations

from pydantic import Field

from shared_core.enums.validation_status import ValidationStatus
from shared_core.schemas.base import BaseSchema


class ValidationResponse(BaseSchema):
    """Payload describing the outcome of a validation run.

    Returned as the ``data`` field of a :class:`SuccessResponse` from
    validation endpoints (e.g. dry-run/validate-only operations).
    """

    status: ValidationStatus
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
