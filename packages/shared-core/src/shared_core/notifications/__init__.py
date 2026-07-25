"""Enterprise Notification Framework.

Multi-channel notification delivery for AI-IOS
(docs/025_Enterprise_Notification_Framework.md.txt "OBJECTIVE"): Email,
SMS, Push, In-App, Slack, Microsoft Teams, Discord, Webhooks. Every
channel implements the same :class:`~shared_core.notifications.channels
.Channel` interface; :class:`~shared_core.notifications.manager
.NotificationManager` (built by :func:`create_notification_framework`)
is the one entry point a service actually calls.
"""

from shared_core.notifications.analytics import NotificationAnalytics
from shared_core.notifications.attachments import (
    Attachment,
    AttachmentKind,
    VirusScanHook,
    kind_from_filename,
    scan_attachment,
    validate_attachment_size,
)
from shared_core.notifications.channels import (
    Channel,
    ChannelRegistry,
    NotificationMessage,
    WebhookUrlResolver,
    build_notification,
    new_notification_id,
)
from shared_core.notifications.decorators import notify_on_failure
from shared_core.notifications.delivery import (
    DeliveryMode,
    DeliveryResult,
    DeliveryStatus,
    build_delivery_result,
)
from shared_core.notifications.digest import Digest, DigestFrequency, DigestGroup, build_digest
from shared_core.notifications.discord import DiscordChannel, build_discord_payload
from shared_core.notifications.dispatcher import NotificationDispatcher
from shared_core.notifications.email import EmailChannel, ToAddressResolver, render_email_body
from shared_core.notifications.exceptions import (
    AttachmentTooLargeError,
    ChannelUnavailableError,
    InvalidPreferenceError,
    RateLimitExceededError,
    SubscriptionError,
    TemplateNotFoundError,
    TemplateRenderError,
    WebhookSignatureError,
)
from shared_core.notifications.factory import create_notification_framework
from shared_core.notifications.health import (
    NotificationHealthReport,
    calculate_notification_health,
    check_http_provider_health,
    check_smtp_health,
    check_webhook_health,
)
from shared_core.notifications.helpers import mask_email, mask_sensitive_metadata, truncate
from shared_core.notifications.history import HistoryEntry, HistoryStore
from shared_core.notifications.in_app import (
    InAppChannel,
    InAppNotificationRecord,
    InAppNotificationStore,
    InAppStatus,
)
from shared_core.notifications.manager import NotificationManager
from shared_core.notifications.metrics import (
    notification_delivery_latency_seconds,
    notifications_bounced_total,
    notifications_clicked_total,
    notifications_delivered_total,
    notifications_failed_total,
    notifications_opened_total,
    notifications_retried_total,
    notifications_sent_total,
    record_bounced,
    record_clicked,
    record_delivered,
    record_failed,
    record_latency,
    record_opened,
    record_retried,
    record_sent,
)
from shared_core.notifications.middleware import (
    DispatchHandler,
    DispatchMiddleware,
    DuplicateSuppressionMiddleware,
    apply_middleware,
    audit_logging_middleware,
)
from shared_core.notifications.preferences import NotificationPreferences, PreferencesStore
from shared_core.notifications.priority import Priority, priority_rank, sort_by_priority
from shared_core.notifications.push import DeviceTokenResolver, PushChannel, build_push_payload
from shared_core.notifications.ratelimit import (
    NotificationRateLimiter,
    build_notification_rate_limiter,
)
from shared_core.notifications.renderer import (
    RenderedNotification,
    preview_template,
    render_template,
    render_to_html,
    validate_template,
)
from shared_core.notifications.retry import (
    DeadLetteredNotification,
    DeadLetterStore,
    RetryPolicy,
    classify_delivery_failure,
    compute_backoff_delay,
    notification_retry_policy,
)
from shared_core.notifications.router import NotificationRouter
from shared_core.notifications.slack import SlackChannel, build_slack_payload
from shared_core.notifications.sms import PhoneNumberResolver, SmsChannel, build_sms_payload
from shared_core.notifications.subscriptions import Subscription, SubscriptionRegistry
from shared_core.notifications.teams import TeamsChannel, build_teams_payload
from shared_core.notifications.templates import Template, TemplateFormat, TemplateRegistry
from shared_core.notifications.tracking import (
    TrackingEvent,
    TrackingRecorder,
    build_click_tracking_url,
    build_open_tracking_url,
)
from shared_core.notifications.webhook import (
    PayloadBuilder,
    WebhookChannel,
    build_webhook_payload,
    sign_payload,
    verify_signature,
)

__all__ = [
    "Attachment",
    "AttachmentKind",
    "AttachmentTooLargeError",
    "Channel",
    "ChannelRegistry",
    "ChannelUnavailableError",
    "DeadLetterStore",
    "DeadLetteredNotification",
    "DeliveryMode",
    "DeliveryResult",
    "DeliveryStatus",
    "DeviceTokenResolver",
    "Digest",
    "DigestFrequency",
    "DigestGroup",
    "DiscordChannel",
    "DispatchHandler",
    "DispatchMiddleware",
    "DuplicateSuppressionMiddleware",
    "EmailChannel",
    "HistoryEntry",
    "HistoryStore",
    "InAppChannel",
    "InAppNotificationRecord",
    "InAppNotificationStore",
    "InAppStatus",
    "InvalidPreferenceError",
    "NotificationAnalytics",
    "NotificationDispatcher",
    "NotificationHealthReport",
    "NotificationManager",
    "NotificationMessage",
    "NotificationPreferences",
    "NotificationRateLimiter",
    "NotificationRouter",
    "PayloadBuilder",
    "PhoneNumberResolver",
    "PreferencesStore",
    "Priority",
    "PushChannel",
    "RateLimitExceededError",
    "RenderedNotification",
    "RetryPolicy",
    "SlackChannel",
    "SmsChannel",
    "Subscription",
    "SubscriptionError",
    "SubscriptionRegistry",
    "TeamsChannel",
    "Template",
    "TemplateFormat",
    "TemplateNotFoundError",
    "TemplateRegistry",
    "TemplateRenderError",
    "ToAddressResolver",
    "TrackingEvent",
    "TrackingRecorder",
    "VirusScanHook",
    "WebhookChannel",
    "WebhookSignatureError",
    "WebhookUrlResolver",
    "apply_middleware",
    "audit_logging_middleware",
    "build_click_tracking_url",
    "build_delivery_result",
    "build_digest",
    "build_discord_payload",
    "build_notification",
    "build_notification_rate_limiter",
    "build_open_tracking_url",
    "build_push_payload",
    "build_slack_payload",
    "build_sms_payload",
    "build_teams_payload",
    "build_webhook_payload",
    "calculate_notification_health",
    "check_http_provider_health",
    "check_smtp_health",
    "check_webhook_health",
    "classify_delivery_failure",
    "compute_backoff_delay",
    "create_notification_framework",
    "kind_from_filename",
    "mask_email",
    "mask_sensitive_metadata",
    "new_notification_id",
    "notification_delivery_latency_seconds",
    "notification_retry_policy",
    "notifications_bounced_total",
    "notifications_clicked_total",
    "notifications_delivered_total",
    "notifications_failed_total",
    "notifications_opened_total",
    "notifications_retried_total",
    "notifications_sent_total",
    "notify_on_failure",
    "preview_template",
    "priority_rank",
    "record_bounced",
    "record_clicked",
    "record_delivered",
    "record_failed",
    "record_latency",
    "record_opened",
    "record_retried",
    "record_sent",
    "render_email_body",
    "render_template",
    "render_to_html",
    "scan_attachment",
    "sign_payload",
    "sort_by_priority",
    "truncate",
    "validate_attachment_size",
    "validate_template",
    "verify_signature",
]
