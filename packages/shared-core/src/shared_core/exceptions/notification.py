"""Notification exception."""

from __future__ import annotations

from shared_core.exceptions.base import AIIOSException


class NotificationError(AIIOSException):
    """Raised when dispatching a notification fails (email, webhook, etc.).

    Retryable: delivery to an external channel is typically a transient
    failure (a bounced SMTP connection, a webhook endpoint timing out).
    """

    error_code = "AIIOS-NOTIFICATION-0001"
    status_code = 502
    severity = "medium"
    retryable = True
    default_user_message = "The notification could not be delivered. It will be retried."
