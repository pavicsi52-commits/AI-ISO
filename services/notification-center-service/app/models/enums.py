"""The platform's fixed notification-center vocabulary (docs/055).

Every ``Mapped[SomeEnum]`` column below is backed by ``String`` at the
database layer, per this repository's established SQLAlchemy 2.0
pattern: a raw string round-trips through Postgres exactly, unlike a
native ``ENUM`` type, which turns every new member into a migration
against a type the whole cluster shares. The cost is that a value freshly
loaded from the database is a plain ``str``, not the enum member -- so
every column that is ever compared, branched on, or handed to another
enum-typed field carries an ``X_of()`` normaliser here, and application
code calls it on the *column*, never on the record that owns it.

**These enums are independent of `shared_core`'s own notification
enums**, even where the vocabulary overlaps (e.g. :class:`NotificationPriority`
duplicates :class:`shared_core.enums.priority.Priority`'s five members
verbatim). This service's own database schema must stay stable across a
`shared_core` version bump that adds or renames a member -- the
``to_shared_*`` translators below are the single place that bridges the
two, mirroring every prior service's ``X_of()``-plus-translator pattern
(e.g. Prompt 054's ``calendar_rule_to_cron``).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final

from shared_core.enums.notification_channel import NotificationChannel as SharedNotificationChannel
from shared_core.enums.notification_type import NotificationType as SharedNotificationType
from shared_core.enums.priority import Priority as SharedPriority
from shared_core.notifications.digest import DigestFrequency as SharedDigestFrequency
from shared_core.notifications.templates import TemplateFormat as SharedTemplateFormat


class NotificationChannelKind(StrEnum):
    """Every delivery channel docs/055 "NOTIFICATION CHANNELS" names.

    Richer than `shared_core`'s own eight-member
    :class:`~shared_core.enums.notification_channel.NotificationChannel`
    -- ``MOBILE_PUSH``/``BROWSER_PUSH`` are two distinct docs/055 channels
    that share `shared_core`'s single ``PUSH`` channel implementation, and
    ``REST_CALLBACK``/``CUSTOM`` are two distinct docs/055 channels that
    share `shared_core`'s webhook-shaped ``WEBHOOK`` channel. See
    :func:`to_shared_channel`.
    """

    EMAIL = "email"
    SMS = "sms"
    SLACK = "slack"
    TEAMS = "teams"
    DISCORD = "discord"
    WEBHOOK = "webhook"
    MOBILE_PUSH = "mobile_push"
    BROWSER_PUSH = "browser_push"
    IN_APP = "in_app"
    REST_CALLBACK = "rest_callback"
    CUSTOM = "custom"


class NotificationCategory(StrEnum):
    """Every notification type docs/055 "NOTIFICATION TYPES" names.

    Richer than `shared_core`'s own
    :class:`~shared_core.enums.notification_type.NotificationType` -- see
    :func:`to_shared_notification_type` for how each maps down to the
    value that actually drives `shared_core`'s router/preferences engine.
    """

    ALERT = "alert"
    WARNING = "warning"
    INFORMATION = "information"
    SUCCESS = "success"
    FAILURE = "failure"
    CRITICAL = "critical"
    REMINDER = "reminder"
    APPROVAL_REQUEST = "approval_request"
    ASSIGNMENT = "assignment"
    SYSTEM_ANNOUNCEMENT = "system_announcement"
    MAINTENANCE_NOTICE = "maintenance_notice"
    DIGEST = "digest"
    CUSTOM = "custom"


class NotificationStatus(StrEnum):
    """A notification's (or one of its deliveries') own lifecycle (docs/055 "DELIVERY TRACKING").

    Extends `shared_core`'s own
    :class:`~shared_core.notifications.delivery.DeliveryStatus` with a
    ``CREATED`` step before anything is queued and an ``ACKNOWLEDGED``
    step docs/055 asks for that `shared_core`'s framework does not model.
    """

    CREATED = "created"
    QUEUED = "queued"
    SENDING = "sending"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    ACKNOWLEDGED = "acknowledged"
    FAILED = "failed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class NotificationPriority(StrEnum):
    """How urgently a notification should be delivered relative to others."""

    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"
    BACKGROUND = "background"


class TemplateFormat(StrEnum):
    """A template's body format (docs/055 "TEMPLATE MANAGEMENT").

    "Rich Templates" are treated as ``HTML`` with structured variables
    rather than a fourth format `shared_core`'s renderer cannot actually
    render -- a documented scope decision, not an omission.
    """

    HTML = "html"
    MARKDOWN = "markdown"
    PLAIN_TEXT = "plain_text"


class DigestFrequency(StrEnum):
    """How often a user's digest is bundled (docs/055 "USER PREFERENCES": "Digest Preferences")."""

    NONE = "none"
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class SubscriptionKind(StrEnum):
    """What a subscription targets (docs/055 "SUBSCRIPTIONS")."""

    EVENT = "event"
    CATEGORY = "category"
    ROLE = "role"
    PROJECT = "project"
    ORGANIZATION = "organization"
    TOPIC = "topic"
    WEBHOOK = "webhook"
    CUSTOM = "custom"


class AnnouncementScope(StrEnum):
    """What an announcement applies to (docs/055 "ANNOUNCEMENTS")."""

    SYSTEM = "system"
    ORGANIZATION = "organization"
    PROJECT = "project"
    MAINTENANCE = "maintenance"


class AnnouncementStatus(StrEnum):
    """An announcement's own publication lifecycle."""

    DRAFT = "draft"
    PUBLISHED = "published"
    EXPIRED = "expired"
    ARCHIVED = "archived"


class BroadcastStatus(StrEnum):
    """One broadcast fan-out operation's own progress."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class ReportKind(StrEnum):
    """Which report a request wants (docs/055 "REPORTING")."""

    DELIVERY = "delivery"
    FAILURE = "failure"
    RETRY = "retry"
    ANNOUNCEMENT = "announcement"
    TEMPLATE_USAGE = "template_usage"
    CHANNEL = "channel"
    ENGAGEMENT = "engagement"
    AUDIT = "audit"


class ReportFormat(StrEnum):
    """How a report is rendered."""

    JSON = "json"
    CSV = "csv"
    MARKDOWN = "markdown"


class ReportStatus(StrEnum):
    """A generated report's own build lifecycle."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AuditAction(StrEnum):
    """What an audit row records (docs/055 "AUDIT")."""

    NOTIFICATION_CREATED = "notification_created"
    NOTIFICATION_SENT = "notification_sent"
    NOTIFICATION_CANCELLED = "notification_cancelled"
    TEMPLATE_CREATED = "template_created"
    TEMPLATE_UPDATED = "template_updated"
    PREFERENCE_UPDATED = "preference_updated"
    SUBSCRIPTION_CREATED = "subscription_created"
    SUBSCRIPTION_REMOVED = "subscription_removed"
    ANNOUNCEMENT_PUBLISHED = "announcement_published"
    ANNOUNCEMENT_UPDATED = "announcement_updated"
    BROADCAST_INITIATED = "broadcast_initiated"
    CHANNEL_CONFIGURED = "channel_configured"
    REPORT_GENERATED = "report_generated"
    ADMINISTRATIVE = "administrative"


# ---- weightings and derivations ----------------------------------------

PRIORITY_ORDER: Final[dict[NotificationPriority, int]] = {
    NotificationPriority.CRITICAL: 0,
    NotificationPriority.HIGH: 1,
    NotificationPriority.NORMAL: 2,
    NotificationPriority.LOW: 3,
    NotificationPriority.BACKGROUND: 4,
}
"""Lower sorts first, so "more urgent" is always "numerically smaller"
without an off-by-one anyone has to remember."""

OPEN_NOTIFICATION_STATUSES: Final[frozenset[NotificationStatus]] = frozenset(
    {
        NotificationStatus.CREATED,
        NotificationStatus.QUEUED,
        NotificationStatus.SENDING,
        NotificationStatus.SENT,
    }
)
"""Statuses that count as "still in flight" -- delivered, read,
acknowledged, failed, expired, and cancelled are all terminal, even
though not every one of those is a success."""

TERMINAL_NOTIFICATION_STATUSES: Final[frozenset[NotificationStatus]] = frozenset(
    {
        NotificationStatus.DELIVERED,
        NotificationStatus.READ,
        NotificationStatus.ACKNOWLEDGED,
        NotificationStatus.FAILED,
        NotificationStatus.EXPIRED,
        NotificationStatus.CANCELLED,
    }
)


def priority_at_least(candidate: NotificationPriority, floor: NotificationPriority) -> bool:
    """Whether *candidate* is at least as urgent as *floor*."""
    return PRIORITY_ORDER[candidate] <= PRIORITY_ORDER[floor]


# ---- translators to shared_core's own vocabulary --------------------------

_CHANNEL_TO_SHARED: Final[dict[NotificationChannelKind, SharedNotificationChannel]] = {
    NotificationChannelKind.EMAIL: SharedNotificationChannel.EMAIL,
    NotificationChannelKind.SMS: SharedNotificationChannel.SMS,
    NotificationChannelKind.SLACK: SharedNotificationChannel.SLACK,
    NotificationChannelKind.TEAMS: SharedNotificationChannel.TEAMS,
    NotificationChannelKind.DISCORD: SharedNotificationChannel.DISCORD,
    NotificationChannelKind.WEBHOOK: SharedNotificationChannel.WEBHOOK,
    NotificationChannelKind.MOBILE_PUSH: SharedNotificationChannel.PUSH,
    NotificationChannelKind.BROWSER_PUSH: SharedNotificationChannel.PUSH,
    NotificationChannelKind.IN_APP: SharedNotificationChannel.IN_APP,
    NotificationChannelKind.REST_CALLBACK: SharedNotificationChannel.WEBHOOK,
    NotificationChannelKind.CUSTOM: SharedNotificationChannel.WEBHOOK,
}


def to_shared_channel(channel: NotificationChannelKind) -> SharedNotificationChannel:
    """Translate this service's own channel vocabulary to `shared_core`'s delivery channel.

    ``MOBILE_PUSH``/``BROWSER_PUSH`` both dispatch through the one
    registered ``PUSH`` channel (a device token vs. a browser
    subscription is a payload detail the channel implementation itself
    resolves, not a distinct wire protocol); ``REST_CALLBACK``/``CUSTOM``
    both dispatch through the one registered ``WEBHOOK`` channel (an
    arbitrary HTTP callback is exactly what `shared_core`'s webhook
    channel already is).
    """
    return _CHANNEL_TO_SHARED[channel]


_CATEGORY_TO_SHARED: Final[dict[NotificationCategory, SharedNotificationType]] = {
    NotificationCategory.ALERT: SharedNotificationType.WARNING,
    NotificationCategory.WARNING: SharedNotificationType.WARNING,
    NotificationCategory.INFORMATION: SharedNotificationType.INFORMATION,
    NotificationCategory.SUCCESS: SharedNotificationType.SUCCESS,
    NotificationCategory.FAILURE: SharedNotificationType.ERROR,
    NotificationCategory.CRITICAL: SharedNotificationType.CRITICAL,
    NotificationCategory.REMINDER: SharedNotificationType.REMINDER,
    NotificationCategory.APPROVAL_REQUEST: SharedNotificationType.APPROVAL,
    NotificationCategory.ASSIGNMENT: SharedNotificationType.WORKFLOW,
    NotificationCategory.SYSTEM_ANNOUNCEMENT: SharedNotificationType.SYSTEM,
    NotificationCategory.MAINTENANCE_NOTICE: SharedNotificationType.MAINTENANCE,
    NotificationCategory.DIGEST: SharedNotificationType.INFORMATION,
    NotificationCategory.CUSTOM: SharedNotificationType.INFORMATION,
}


def to_shared_notification_type(category: NotificationCategory) -> SharedNotificationType:
    """Translate this service's own category vocabulary to `shared_core`'s notification type.

    `shared_core`'s router and preferences engine key every allow/mute
    decision off :class:`~shared_core.enums.notification_type
    .NotificationType`, which has no ``ALERT``/``FAILURE``/``ASSIGNMENT``/
    ``DIGEST``/``CUSTOM`` member of its own -- each maps to the closest
    existing member (an alert is an attention-worthy, non-fatal warning;
    a failure is an error; an assignment is a workflow handoff; a digest
    or custom notification's own content is informational) rather than
    growing `shared_core`'s vocabulary for one service's naming choices.
    """
    return _CATEGORY_TO_SHARED[category]


_PRIORITY_TO_SHARED: Final[dict[NotificationPriority, SharedPriority]] = {
    NotificationPriority.CRITICAL: SharedPriority.CRITICAL,
    NotificationPriority.HIGH: SharedPriority.HIGH,
    NotificationPriority.NORMAL: SharedPriority.NORMAL,
    NotificationPriority.LOW: SharedPriority.LOW,
    NotificationPriority.BACKGROUND: SharedPriority.BACKGROUND,
}


def to_shared_priority(priority: NotificationPriority) -> SharedPriority:
    """Translate this service's own priority to `shared_core`'s (a direct, one-to-one mapping)."""
    return _PRIORITY_TO_SHARED[priority]


_TEMPLATE_FORMAT_TO_SHARED: Final[dict[TemplateFormat, SharedTemplateFormat]] = {
    TemplateFormat.HTML: SharedTemplateFormat.HTML,
    TemplateFormat.MARKDOWN: SharedTemplateFormat.MARKDOWN,
    TemplateFormat.PLAIN_TEXT: SharedTemplateFormat.PLAIN_TEXT,
}


def to_shared_template_format(template_format: TemplateFormat) -> SharedTemplateFormat:
    """Translate this service's own template format to `shared_core`'s (direct, one-to-one)."""
    return _TEMPLATE_FORMAT_TO_SHARED[template_format]


_DIGEST_FREQUENCY_TO_SHARED: Final[dict[DigestFrequency, SharedDigestFrequency]] = {
    DigestFrequency.NONE: SharedDigestFrequency.NONE,
    DigestFrequency.HOURLY: SharedDigestFrequency.HOURLY,
    DigestFrequency.DAILY: SharedDigestFrequency.DAILY,
    DigestFrequency.WEEKLY: SharedDigestFrequency.WEEKLY,
    DigestFrequency.MONTHLY: SharedDigestFrequency.MONTHLY,
}


def to_shared_digest_frequency(frequency: DigestFrequency) -> SharedDigestFrequency:
    """Translate this service's own digest frequency to `shared_core`'s (direct, one-to-one)."""
    return _DIGEST_FREQUENCY_TO_SHARED[frequency]


# ---- normalisers ---------------------------------------------------------


def notification_channel_kind_of(value: str | NotificationChannelKind) -> NotificationChannelKind:
    """Coerce a stored value to :class:`NotificationChannelKind`."""
    return value if isinstance(value, NotificationChannelKind) else NotificationChannelKind(value)


def notification_category_of(value: str | NotificationCategory) -> NotificationCategory:
    """Coerce a stored value to :class:`NotificationCategory`."""
    return value if isinstance(value, NotificationCategory) else NotificationCategory(value)


def notification_status_of(value: str | NotificationStatus) -> NotificationStatus:
    """Coerce a stored value to :class:`NotificationStatus`."""
    return value if isinstance(value, NotificationStatus) else NotificationStatus(value)


def notification_priority_of(value: str | NotificationPriority) -> NotificationPriority:
    """Coerce a stored value to :class:`NotificationPriority`."""
    return value if isinstance(value, NotificationPriority) else NotificationPriority(value)


def template_format_of(value: str | TemplateFormat) -> TemplateFormat:
    """Coerce a stored value to :class:`TemplateFormat`."""
    return value if isinstance(value, TemplateFormat) else TemplateFormat(value)


def digest_frequency_of(value: str | DigestFrequency) -> DigestFrequency:
    """Coerce a stored value to :class:`DigestFrequency`."""
    return value if isinstance(value, DigestFrequency) else DigestFrequency(value)


def subscription_kind_of(value: str | SubscriptionKind) -> SubscriptionKind:
    """Coerce a stored value to :class:`SubscriptionKind`."""
    return value if isinstance(value, SubscriptionKind) else SubscriptionKind(value)


def announcement_scope_of(value: str | AnnouncementScope) -> AnnouncementScope:
    """Coerce a stored value to :class:`AnnouncementScope`."""
    return value if isinstance(value, AnnouncementScope) else AnnouncementScope(value)


def announcement_status_of(value: str | AnnouncementStatus) -> AnnouncementStatus:
    """Coerce a stored value to :class:`AnnouncementStatus`."""
    return value if isinstance(value, AnnouncementStatus) else AnnouncementStatus(value)


def broadcast_status_of(value: str | BroadcastStatus) -> BroadcastStatus:
    """Coerce a stored value to :class:`BroadcastStatus`."""
    return value if isinstance(value, BroadcastStatus) else BroadcastStatus(value)


def report_kind_of(value: str | ReportKind) -> ReportKind:
    """Coerce a stored value to :class:`ReportKind`."""
    return value if isinstance(value, ReportKind) else ReportKind(value)


def report_format_of(value: str | ReportFormat) -> ReportFormat:
    """Coerce a stored value to :class:`ReportFormat`."""
    return value if isinstance(value, ReportFormat) else ReportFormat(value)


def report_status_of(value: str | ReportStatus) -> ReportStatus:
    """Coerce a stored value to :class:`ReportStatus`."""
    return value if isinstance(value, ReportStatus) else ReportStatus(value)


__all__ = [
    "OPEN_NOTIFICATION_STATUSES",
    "PRIORITY_ORDER",
    "TERMINAL_NOTIFICATION_STATUSES",
    "AnnouncementScope",
    "AnnouncementStatus",
    "AuditAction",
    "BroadcastStatus",
    "DigestFrequency",
    "NotificationCategory",
    "NotificationChannelKind",
    "NotificationPriority",
    "NotificationStatus",
    "ReportFormat",
    "ReportKind",
    "ReportStatus",
    "SubscriptionKind",
    "TemplateFormat",
    "announcement_scope_of",
    "announcement_status_of",
    "broadcast_status_of",
    "digest_frequency_of",
    "notification_category_of",
    "notification_channel_kind_of",
    "notification_priority_of",
    "notification_status_of",
    "priority_at_least",
    "report_format_of",
    "report_kind_of",
    "report_status_of",
    "subscription_kind_of",
    "template_format_of",
    "to_shared_channel",
    "to_shared_digest_frequency",
    "to_shared_notification_type",
    "to_shared_priority",
    "to_shared_template_format",
]
