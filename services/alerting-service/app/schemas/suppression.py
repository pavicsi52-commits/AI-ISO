"""Request/response schemas for ``/alert-suppressions``.

Docs/045's own literal REST list names no suppression endpoint (only
``/maintenance-windows``, which is one of seven suppression types),
yet "Suppression" is an explicit ACCEPTANCE CRITERIA line and the
remaining six types have no other way to be configured. Added
directly, the same "required capability, no REST list entry"
precedent every prior AI-IOS service has established at least once.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import SuppressionType


class SuppressionCreateRequest(BaseModel):
    """Body of ``POST /alert-suppressions``."""

    organization_id: UUID
    project_id: UUID | None = None
    suppression_type: SuppressionType
    scope_reference: str | None = Field(
        default=None,
        max_length=255,
        description=(
            "What to suppress -- matched against an alert's own "
            "source_reference values. Omit to suppress organization-wide."
        ),
    )
    reason: str | None = None
    starts_at: datetime
    ends_at: datetime | None = Field(
        default=None, description="Omit for an open-ended suppression."
    )
    enabled: bool = True


class SuppressionResponse(BaseModel):
    """One suppression rule."""

    id: UUID
    organization_id: UUID
    project_id: UUID | None
    suppression_type: SuppressionType
    scope_reference: str | None
    reason: str | None
    created_by: UUID | None
    starts_at: datetime
    ends_at: datetime | None
    enabled: bool


__all__ = ["SuppressionCreateRequest", "SuppressionResponse"]
