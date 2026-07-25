"""Notification-framework-specific exceptions.

Each subclasses :class:`shared_core.exceptions.notification.NotificationError`
so a bare ``except NotificationError`` still catches everything raised
anywhere in this framework. Not registered in
:mod:`shared_core.exceptions.constants`'s central catalog -- same
reasoning as every other Prompt 018-024 framework: that module would
need to import from here, and this module already imports from
``shared_core.exceptions.notification``, so a back-import would cycle.
Error codes are manually kept unique in the ``AIIOS-NOTIFICATION-*``
range against the base class's ``AIIOS-NOTIFICATION-0001``.
"""

from __future__ import annotations

from shared_core.exceptions.notification import NotificationError


class ChannelUnavailableError(NotificationError):
    """Raised when a requested delivery channel isn't configured or reachable."""

    error_code = "AIIOS-NOTIFICATION-0002"
    status_code = 503
    retryable = True
    default_user_message = "The requested notification channel is currently unavailable."


class TemplateRenderError(NotificationError):
    """Raised when rendering a notification template fails."""

    error_code = "AIIOS-NOTIFICATION-0003"
    status_code = 500
    retryable = False
    default_user_message = "The notification template could not be rendered."


class TemplateNotFoundError(NotificationError):
    """Raised when a referenced template isn't registered."""

    error_code = "AIIOS-NOTIFICATION-0004"
    status_code = 404
    retryable = False
    default_user_message = "The requested notification template does not exist."


class RateLimitExceededError(NotificationError):
    """Raised when a notification is rejected by a rate limit."""

    error_code = "AIIOS-NOTIFICATION-0005"
    status_code = 429
    retryable = True
    default_user_message = "Too many notifications sent recently. Please try again later."


class InvalidPreferenceError(NotificationError):
    """Raised when a user preference value is invalid (e.g. an unknown channel)."""

    error_code = "AIIOS-NOTIFICATION-0006"
    status_code = 422
    retryable = False
    default_user_message = "The notification preference value is invalid."


class WebhookSignatureError(NotificationError):
    """Raised when a webhook payload fails signature verification."""

    error_code = "AIIOS-NOTIFICATION-0007"
    status_code = 401
    retryable = False
    default_user_message = "The webhook signature could not be verified."


class AttachmentTooLargeError(NotificationError):
    """Raised when an attachment exceeds the configured maximum size."""

    error_code = "AIIOS-NOTIFICATION-0008"
    status_code = 413
    retryable = False
    default_user_message = "The attachment exceeds the maximum allowed size."


class SubscriptionError(NotificationError):
    """Raised when a subscribe/unsubscribe operation fails."""

    error_code = "AIIOS-NOTIFICATION-0009"
    status_code = 500
    retryable = False
    default_user_message = "The subscription request could not be completed."


__all__ = [
    "AttachmentTooLargeError",
    "ChannelUnavailableError",
    "InvalidPreferenceError",
    "RateLimitExceededError",
    "SubscriptionError",
    "TemplateNotFoundError",
    "TemplateRenderError",
    "WebhookSignatureError",
]
