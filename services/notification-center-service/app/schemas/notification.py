"""Request and response schemas for the notification-center API surface."""

from __future__ import annotations

from datetime import datetime, time
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import (
    AnnouncementScope,
    AnnouncementStatus,
    AuditAction,
    BroadcastStatus,
    DigestFrequency,
    NotificationCategory,
    NotificationChannelKind,
    NotificationPriority,
    NotificationStatus,
    ReportFormat,
    ReportKind,
    ReportStatus,
    SubscriptionKind,
    TemplateFormat,
)

# ---- notifications ------------------------------------------------------------


class NotificationCreateRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=255)
    category: NotificationCategory = NotificationCategory.INFORMATION
    priority: NotificationPriority = NotificationPriority.NORMAL
    body: str = Field(min_length=1)
    subject: str | None = Field(default=None, max_length=255)
    template_id: UUID | None = None
    template_variables: dict[str, Any] = Field(default_factory=dict)
    source_service: str = Field(min_length=1, max_length=128)
    source_event_type: str | None = None
    correlation_id: str | None = None
    expires_at: datetime | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class NotificationSendRequest(NotificationCreateRequest):
    channel: NotificationChannelKind | None = None
    """An explicit channel to deliver over; otherwise resolved from the recipient's own preferences."""  # noqa: E501


class NotificationResponse(BaseModel):
    id: UUID
    organization_id: UUID
    user_id: str
    category: NotificationCategory
    priority: NotificationPriority
    status: NotificationStatus
    subject: str | None
    body: str
    template_id: UUID | None
    source_service: str
    source_event_type: str | None
    correlation_id: str | None
    expires_at: datetime | None
    read_at: datetime | None
    acknowledged_at: datetime | None
    tags: list[str]
    notification_metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class NotificationBroadcastRequest(BaseModel):
    body: str = Field(min_length=1)
    category: NotificationCategory = NotificationCategory.SYSTEM_ANNOUNCEMENT
    priority: NotificationPriority = NotificationPriority.NORMAL
    subject: str | None = None
    channel: NotificationChannelKind | None = None
    topic: str | None = None
    recipient_user_ids: list[str] = Field(default_factory=list)
    announcement_id: UUID | None = None


class BroadcastResponse(BaseModel):
    id: UUID
    organization_id: UUID
    announcement_id: UUID | None
    topic: str | None
    category: NotificationCategory
    priority: NotificationPriority
    channel: NotificationChannelKind | None
    subject: str | None
    body: str
    status: BroadcastStatus
    total_recipients: int
    sent_count: int
    failed_count: int
    initiated_by: str | None
    initiated_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


# ---- preferences --------------------------------------------------------------


class PreferenceUpdateRequest(BaseModel):
    preferred_channels: list[NotificationChannelKind] | None = None
    muted_categories: list[NotificationCategory] | None = None
    unsubscribed_channels: list[NotificationChannelKind] | None = None
    channel_priority: list[NotificationChannelKind] | None = None
    device_tokens: list[str] | None = None
    quiet_hours_start: time | None = None
    quiet_hours_end: time | None = None
    language: str | None = None
    timezone: str | None = None
    digest_frequency: DigestFrequency | None = None
    muted: bool | None = None
    priority_overrides: dict[str, Any] | None = None


class PreferenceResponse(BaseModel):
    id: UUID
    organization_id: UUID
    user_id: str
    preferred_channels: list[str]
    muted_categories: list[str]
    unsubscribed_channels: list[str]
    channel_priority: list[str]
    device_tokens: list[str]
    quiet_hours_start: time | None
    quiet_hours_end: time | None
    language: str
    timezone: str
    digest_frequency: DigestFrequency
    muted: bool
    priority_overrides: dict[str, Any]

    model_config = {"from_attributes": True}


# ---- templates ----------------------------------------------------------------


class TemplateCreateRequest(BaseModel):
    template_key: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    body_template: str = Field(min_length=1)
    format: TemplateFormat = TemplateFormat.PLAIN_TEXT
    description: str | None = None
    category: NotificationCategory | None = None
    locale: str = "en"
    subject_template: str | None = None


class TemplateUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    category: NotificationCategory | None = None
    body_template: str | None = None
    subject_template: str | None = None
    format: TemplateFormat | None = None
    is_active: bool | None = None
    change_note: str | None = None


class TemplateResponse(BaseModel):
    id: UUID
    organization_id: UUID
    template_key: str
    name: str
    description: str | None
    category: NotificationCategory | None
    format: TemplateFormat
    locale: str
    subject_template: str | None
    body_template: str
    current_version: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TemplateVersionResponse(BaseModel):
    id: UUID
    template_id: UUID
    version: int
    subject_template: str | None
    body_template: str
    format: TemplateFormat
    change_note: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TemplatePreviewRequest(BaseModel):
    variables: dict[str, Any] = Field(default_factory=dict)


class TemplatePreviewResponse(BaseModel):
    subject: str | None
    body: str
    format: TemplateFormat


# ---- subscriptions --------------------------------------------------------------


class SubscriptionCreateRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=255)
    subscription_kind: SubscriptionKind
    target: str = Field(min_length=1, max_length=255)
    webhook_url: str | None = None


class SubscriptionResponse(BaseModel):
    id: UUID
    organization_id: UUID
    user_id: str
    subscription_kind: SubscriptionKind
    target: str
    webhook_url: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ---- channels -------------------------------------------------------------------


class ChannelConfigRequest(BaseModel):
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)
    description: str | None = None


class ChannelConfigResponse(BaseModel):
    id: UUID
    organization_id: UUID
    channel: NotificationChannelKind
    enabled: bool
    config: dict[str, Any]
    description: str | None

    model_config = {"from_attributes": True}


# ---- deliveries and dead letters ------------------------------------------------


class DeliveryResponse(BaseModel):
    id: UUID
    notification_id: UUID
    channel: NotificationChannelKind
    status: NotificationStatus
    queued_at: datetime
    sent_at: datetime | None
    delivered_at: datetime | None
    failed_at: datetime | None
    attempts_used: int
    provider_message_id: str | None
    error: str | None
    latency_ms: float | None

    model_config = {"from_attributes": True}


class DeliveryAttemptResponse(BaseModel):
    id: UUID
    delivery_id: UUID
    attempt_number: int
    status: NotificationStatus
    attempted_at: datetime
    completed_at: datetime | None
    error: str | None
    latency_ms: float | None

    model_config = {"from_attributes": True}


class DeadLetterResponse(BaseModel):
    id: UUID
    notification_id: UUID
    delivery_id: UUID
    channel: NotificationChannelKind
    attempts: int
    last_error: str | None
    dead_lettered_at: datetime
    resolved: bool
    resolved_at: datetime | None
    resolution_note: str | None

    model_config = {"from_attributes": True}


# ---- announcements ----------------------------------------------------------------


class AnnouncementCreateRequest(BaseModel):
    scope: AnnouncementScope
    title: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1)
    is_pinned: bool = False
    starts_at: datetime | None = None
    expires_at: datetime | None = None
    audience: dict[str, Any] = Field(default_factory=dict)


class AnnouncementUpdateRequest(BaseModel):
    title: str | None = None
    body: str | None = None
    is_pinned: bool | None = None
    starts_at: datetime | None = None
    expires_at: datetime | None = None
    audience: dict[str, Any] | None = None


class AnnouncementResponse(BaseModel):
    id: UUID
    organization_id: UUID
    scope: AnnouncementScope
    status: AnnouncementStatus
    title: str
    body: str
    is_pinned: bool
    starts_at: datetime | None
    expires_at: datetime | None
    published_at: datetime | None
    audience: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---- statistics, reports, audit --------------------------------------------------


class StatisticResponse(BaseModel):
    id: UUID
    window_start: datetime
    window_end: datetime
    sent_count: int
    delivered_count: int
    failed_count: int
    read_count: int
    acknowledged_count: int
    retried_count: int
    average_delivery_ms: float | None
    read_rate: float
    acknowledgement_rate: float
    retry_rate: float
    channel_usage: dict[str, int]
    template_usage: dict[str, int]

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
    "AnnouncementCreateRequest",
    "AnnouncementResponse",
    "AnnouncementUpdateRequest",
    "AuditEntryResponse",
    "BroadcastResponse",
    "ChannelConfigRequest",
    "ChannelConfigResponse",
    "DeadLetterResponse",
    "DeliveryAttemptResponse",
    "DeliveryResponse",
    "NotificationBroadcastRequest",
    "NotificationCreateRequest",
    "NotificationResponse",
    "NotificationSendRequest",
    "PreferenceResponse",
    "PreferenceUpdateRequest",
    "ReportGenerateRequest",
    "ReportResponse",
    "StatisticResponse",
    "SubscriptionCreateRequest",
    "SubscriptionResponse",
    "TemplateCreateRequest",
    "TemplatePreviewRequest",
    "TemplatePreviewResponse",
    "TemplateResponse",
    "TemplateUpdateRequest",
    "TemplateVersionResponse",
]
