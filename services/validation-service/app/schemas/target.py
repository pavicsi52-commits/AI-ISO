"""Request/response schemas for validation targets.

``TargetReference`` is what a caller supplies inline inside
``POST /validations/{id}/execute``'s own request body -- docs/043's own
literal REST APIs list names no dedicated ``/validation-targets``
endpoint, and "INVENTORY INTEGRATION"'s own "Dynamic Inventory" support
means targets are resolved from another service's own live state at
execution time, not pre-registered through a CRUD form of their own.
:meth:`~app.services.target.ValidationTargetService.get_or_create`
uses ``(target_type, external_id)`` to reuse the same
:class:`~app.models.validation_target.ValidationTarget` row across
repeated executions of the same real asset rather than registering a
fresh duplicate every time.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import ValidationTargetType


class TargetReference(BaseModel):
    """One target to validate, identified in its own owning service."""

    target_type: ValidationTargetType
    external_id: str = Field(min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=255)
    target_metadata: dict[str, Any] = Field(default_factory=dict)


class ValidationTargetResponse(BaseModel):
    """One registered validation target."""

    id: UUID
    organization_id: UUID
    project_id: UUID | None
    target_type: ValidationTargetType
    external_id: str
    name: str
    target_metadata: dict[str, Any]


__all__ = ["TargetReference", "ValidationTargetResponse"]
