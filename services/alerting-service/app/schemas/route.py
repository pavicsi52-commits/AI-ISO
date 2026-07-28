"""Request/response schemas for ``/alert-routes``.

Docs/045's own literal REST list names no ``/alert-routes`` endpoint,
yet "Routing" is an explicit ACCEPTANCE CRITERIA line and every alert
delivery depends on a configured route existing. Added directly, the
same "required capability, no REST list entry" precedent every prior
AI-IOS service has established at least once.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field
from shared_core.enums.severity import Severity

from app.models.enums import AlertRouteChannel, RouteTargetType


class AlertRouteCreateRequest(BaseModel):
    """Body of ``POST /alert-routes``."""

    organization_id: UUID
    project_id: UUID | None = None
    name: str = Field(min_length=1, max_length=255)
    channel: AlertRouteChannel
    target_type: RouteTargetType
    target_reference: str = Field(min_length=1, max_length=255)
    configuration: dict[str, Any] = Field(default_factory=dict)
    severity_filter: Severity | None = Field(
        default=None,
        description=(
            "Minimum severity this route fires for. A route filtered at HIGH "
            "also fires for CRITICAL. Omit to match every severity."
        ),
    )
    enabled: bool = True


class AlertRouteResponse(BaseModel):
    """One routing configuration."""

    id: UUID
    organization_id: UUID
    project_id: UUID | None
    name: str
    channel: AlertRouteChannel
    target_type: RouteTargetType
    target_reference: str
    configuration: dict[str, Any]
    severity_filter: Severity | None
    enabled: bool


__all__ = ["AlertRouteCreateRequest", "AlertRouteResponse"]
