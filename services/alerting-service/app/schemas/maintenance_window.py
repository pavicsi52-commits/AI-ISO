"""Request/response schemas for ``/maintenance-windows``."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import MaintenanceWindowScope, MaintenanceWindowType


class MaintenanceWindowCreateRequest(BaseModel):
    """Body of ``POST /maintenance-windows``."""

    organization_id: UUID
    project_id: UUID | None = None
    name: str = Field(min_length=1, max_length=255)
    window_type: MaintenanceWindowType
    scope: MaintenanceWindowScope
    scope_reference: str | None = Field(default=None, max_length=255)
    recurrence_rule: str | None = Field(
        default=None,
        description=(
            "Recurrence for RECURRING windows, e.g. 'FREQ=WEEKLY' or "
            "'FREQ=DAILY;INTERVAL=2'. Supported frequencies: DAILY, WEEKLY, MONTHLY."
        ),
    )
    starts_at: datetime
    ends_at: datetime
    enabled: bool = True


class MaintenanceWindowResponse(BaseModel):
    """One maintenance window."""

    id: UUID
    organization_id: UUID
    project_id: UUID | None
    name: str
    window_type: MaintenanceWindowType
    scope: MaintenanceWindowScope
    scope_reference: str | None
    recurrence_rule: str | None
    starts_at: datetime
    ends_at: datetime
    enabled: bool


__all__ = ["MaintenanceWindowCreateRequest", "MaintenanceWindowResponse"]
