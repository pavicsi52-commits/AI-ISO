"""Request/response schemas for ``/alerts``."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field
from shared_core.enums.severity import Severity

from app.models.enums import AlertSource, AlertStatus


class AlertCreateRequest(BaseModel):
    """Body of ``POST /alerts`` -- raise an alert directly.

    ``rule_id`` is optional: an alert may be raised by a caller that
    already decided a condition holds (e.g. another AI-IOS service
    forwarding its own event), without this service's own rule engine
    being involved.
    """

    organization_id: UUID
    project_id: UUID | None = None
    rule_id: UUID | None = None
    source: AlertSource
    severity: Severity
    title: str = Field(min_length=1, max_length=255)
    message: str = Field(min_length=1)
    source_reference: dict[str, Any] = Field(default_factory=dict)


class AlertUpdateRequest(BaseModel):
    """Body of ``PUT /alerts/{id}``."""

    severity: Severity | None = None
    title: str | None = Field(default=None, min_length=1, max_length=255)
    message: str | None = Field(default=None, min_length=1)
    assigned_to: UUID | None = None


class AlertAcknowledgeRequest(BaseModel):
    """Body of ``POST /alerts/{id}/acknowledge``."""

    comment: str | None = None


class AlertResolveRequest(BaseModel):
    """Body of ``POST /alerts/{id}/resolve``."""

    resolution_notes: str | None = None


class AlertEscalateRequest(BaseModel):
    """Body of ``POST /alerts/{id}/escalate``.

    ``policy_id`` is optional -- omitted, the alert is escalated
    manually (status change plus history entry) without walking a
    stored policy's own level chain.
    """

    policy_id: UUID | None = None
    reason: str | None = None


class AlertResponse(BaseModel):
    """One fired alert."""

    id: UUID
    organization_id: UUID
    project_id: UUID | None
    rule_id: UUID | None
    source: AlertSource
    severity: Severity
    status: AlertStatus
    title: str
    message: str
    fingerprint: str
    source_reference: dict[str, Any]
    assigned_to: UUID | None
    triggered_at: datetime
    resolved_at: datetime | None
    closed_at: datetime | None


class AlertHistoryResponse(BaseModel):
    """One status transition in an alert's own lifecycle."""

    id: UUID
    alert_id: UUID
    from_status: AlertStatus | None
    to_status: AlertStatus
    changed_by: UUID | None
    reason: str | None
    changed_at: datetime


__all__ = [
    "AlertAcknowledgeRequest",
    "AlertCreateRequest",
    "AlertEscalateRequest",
    "AlertHistoryResponse",
    "AlertResolveRequest",
    "AlertResponse",
    "AlertUpdateRequest",
]
