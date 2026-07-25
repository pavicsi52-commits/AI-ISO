"""Notification type enumeration."""

from enum import StrEnum


class NotificationType(StrEnum):
    """The kind of event a notification represents.

    Per docs/025_Enterprise_Notification_Framework.md.txt "NOTIFICATION
    TYPES". Distinct from :class:`~shared_core.enums.notification_channel
    .NotificationChannel` (*how* it's delivered) -- this is *what kind*
    of event it is. Repurposed from the Prompt 012 baseline, which held
    a small channel-flavored value set (``toast``/``email``/``in_app``/
    ``webhook``/``sms``) as a placeholder before this prompt's spec
    existed to clarify the two concepts are separate; that channel list
    now lives, complete, in ``NotificationChannel``.
    """

    INFORMATION = "information"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"
    APPROVAL = "approval"
    REMINDER = "reminder"
    SYSTEM = "system"
    WORKFLOW = "workflow"
    AUTOMATION = "automation"
    VALIDATION = "validation"
    MONITORING = "monitoring"
    SECURITY = "security"
    AI = "ai"
    MAINTENANCE = "maintenance"
