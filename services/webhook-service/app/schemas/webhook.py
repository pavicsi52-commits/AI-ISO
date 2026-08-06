"""Request and response schemas for the webhook service's own management surface."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import (
    AuditAction,
    DeliveryMode,
    DeliveryStatus,
    EndpointStatus,
    EventSource,
    FilterMatchMode,
    ReplayScope,
    ReplayStatus,
    ReportFormat,
    ReportKind,
    ReportStatus,
    SignatureAlgorithm,
    SubscriptionScope,
    WebhookAuthMethod,
    WebhookKind,
)

# ---- endpoints ------------------------------------------------------------------


class EndpointCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    url: str = Field(min_length=1, max_length=2048)
    kind: WebhookKind = WebhookKind.OUTGOING
    auth_method: WebhookAuthMethod = WebhookAuthMethod.HMAC_SHA256
    description: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    owner_id: str | None = None
    timeout_seconds: float | None = Field(default=None, gt=0)
    max_attempts: int | None = Field(default=None, ge=1, le=50)


class EndpointUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    url: str | None = None
    auth_method: WebhookAuthMethod | None = None
    headers: dict[str, str] | None = None
    status: EndpointStatus | None = None
    owner_id: str | None = None
    timeout_seconds: float | None = Field(default=None, gt=0)
    max_attempts: int | None = Field(default=None, ge=1, le=50)
    backoff_strategy: str | None = None
    enabled: bool | None = None


class EndpointResponse(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    description: str | None
    url: str
    kind: WebhookKind
    auth_method: WebhookAuthMethod
    headers: dict[str, str]
    status: EndpointStatus
    owner_id: str | None
    timeout_seconds: float | None
    max_attempts: int | None
    consecutive_failures: int
    enabled: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ---- subscriptions --------------------------------------------------------------


class SubscriptionCreateRequest(BaseModel):
    endpoint_id: UUID
    scope: SubscriptionScope
    scope_reference: str | None = None
    event_types: list[str] = Field(default_factory=list)
    condition_expression: str | None = None


class SubscriptionUpdateRequest(BaseModel):
    scope_reference: str | None = None
    event_types: list[str] | None = None
    condition_expression: str | None = None
    enabled: bool | None = None


class SubscriptionResponse(BaseModel):
    id: UUID
    organization_id: UUID
    endpoint_id: UUID
    scope: SubscriptionScope
    scope_reference: str | None
    event_types: list[str]
    condition_expression: str | None
    enabled: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ---- filters ---------------------------------------------------------------------


class FilterCreateRequest(BaseModel):
    subscription_id: UUID
    name: str = Field(min_length=1, max_length=128)
    match_mode: FilterMatchMode = FilterMatchMode.ALL
    rules: list[dict[str, Any]] = Field(default_factory=list)


class FilterResponse(BaseModel):
    id: UUID
    subscription_id: UUID
    name: str
    match_mode: FilterMatchMode
    rules: list[dict[str, Any]]
    enabled: bool

    model_config = {"from_attributes": True}


# ---- transformations --------------------------------------------------------------


class TransformationCreateRequest(BaseModel):
    endpoint_id: UUID
    name: str = Field(min_length=1, max_length=128)
    kind: str
    config: dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=100, ge=0, le=100_000)


class TransformationResponse(BaseModel):
    id: UUID
    endpoint_id: UUID
    name: str
    kind: str
    config: dict[str, Any]
    priority: int
    enabled: bool

    model_config = {"from_attributes": True}


# ---- signatures --------------------------------------------------------------------


class SignatureCreateRequest(BaseModel):
    endpoint_id: UUID
    secret: str = Field(min_length=8, max_length=512)
    algorithm: SignatureAlgorithm = SignatureAlgorithm.HMAC_SHA256


class SignatureRotateRequest(BaseModel):
    endpoint_id: UUID
    new_secret: str = Field(min_length=8, max_length=512)
    overlap_hours: int = Field(default=24, ge=0, le=720)


class SignatureResponse(BaseModel):
    id: UUID
    endpoint_id: UUID
    version: int
    algorithm: SignatureAlgorithm
    status: str
    expires_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ---- events and incoming/outgoing ------------------------------------------------


class InternalEventRequest(BaseModel):
    source: EventSource
    event_type: str = Field(min_length=1, max_length=128)
    payload: dict[str, Any] = Field(default_factory=dict)
    severity: str | None = None
    status: str | None = None
    tags: list[str] = Field(default_factory=list)
    labels: dict[str, str] = Field(default_factory=dict)
    idempotency_key: str | None = None
    correlation_id: str | None = None


class EventResponse(BaseModel):
    id: UUID
    organization_id: UUID
    kind: WebhookKind
    source: EventSource
    event_type: str
    severity: str | None
    status: str | None
    tags: list[str]
    labels: dict[str, str]
    payload: dict[str, Any]
    idempotency_key: str | None
    correlation_id: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class OutgoingDeliveryRequest(BaseModel):
    """Directly queues a delivery for one endpoint, bypassing subscription fan-out --
    for a caller that already knows exactly which endpoint should receive this payload."""

    endpoint_id: UUID
    event_type: str = Field(min_length=1, max_length=128)
    payload: dict[str, Any] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    idempotency_key: str | None = None


# ---- deliveries --------------------------------------------------------------------


class DeliveryResponse(BaseModel):
    id: UUID
    organization_id: UUID
    event_id: UUID
    endpoint_id: UUID
    subscription_id: UUID | None
    mode: DeliveryMode
    status: DeliveryStatus
    attempt_count: int
    max_attempts: int
    delivered_at: datetime | None
    last_error: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ---- replay --------------------------------------------------------------------------


class ReplayCreateRequest(BaseModel):
    scope: ReplayScope
    event_id: UUID | None = None
    endpoint_id: UUID | None = None
    subscription_id: UUID | None = None
    date_range_start: datetime | None = None
    date_range_end: datetime | None = None
    dry_run: bool = False


class ReplayResponse(BaseModel):
    id: UUID
    organization_id: UUID
    scope: ReplayScope
    status: ReplayStatus
    dry_run: bool
    matched_count: int
    replayed_count: int
    failed_count: int
    error: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ---- statistics, reports, audit --------------------------------------------------


class StatisticResponse(BaseModel):
    id: UUID
    window_start: datetime
    window_end: datetime
    deliveries_attempted: int
    deliveries_succeeded: int
    deliveries_failed: int
    retries: int
    average_latency_ms: float | None
    p95_latency_ms: float | None
    success_rate: float
    by_endpoint: dict[str, int]

    model_config = {"from_attributes": True}


class ReportGenerateRequest(BaseModel):
    kind: ReportKind
    report_format: ReportFormat = ReportFormat.JSON
    title: str | None = None


class ReportResponse(BaseModel):
    id: UUID
    kind: ReportKind
    report_format: ReportFormat
    title: str
    status: ReportStatus
    content: dict[str, Any]
    row_count: int | None
    generated_by: str | None
    generated_at: datetime | None
    duration_ms: float | None
    error: str | None

    model_config = {"from_attributes": True}


class AuditEntryResponse(BaseModel):
    id: UUID
    action: AuditAction
    entity_type: str
    entity_id: UUID | None
    entity_reference: str | None
    actor_id: str | None
    actor_type: str
    occurred_at: datetime
    summary: str
    succeeded: bool
    changes: dict[str, Any]
    context: dict[str, Any]

    model_config = {"from_attributes": True}


__all__ = [
    "AuditEntryResponse",
    "DeliveryResponse",
    "EndpointCreateRequest",
    "EndpointResponse",
    "EndpointUpdateRequest",
    "EventResponse",
    "FilterCreateRequest",
    "FilterResponse",
    "InternalEventRequest",
    "OutgoingDeliveryRequest",
    "ReplayCreateRequest",
    "ReplayResponse",
    "ReportGenerateRequest",
    "ReportResponse",
    "SignatureCreateRequest",
    "SignatureResponse",
    "SignatureRotateRequest",
    "StatisticResponse",
    "SubscriptionCreateRequest",
    "SubscriptionResponse",
    "SubscriptionUpdateRequest",
    "TransformationCreateRequest",
    "TransformationResponse",
]
