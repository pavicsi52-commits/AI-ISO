"""Message queue exception."""

from __future__ import annotations

from shared_core.exceptions.base import AIIOSException


class QueueError(AIIOSException):
    """Raised when a message queue operation fails (RabbitMQ).

    Per docs/015 "RETRY POLICY": RabbitMQ failures are retryable.
    """

    error_code = "AIIOS-QUEUE-0001"
    status_code = 503
    severity = "high"
    retryable = True
    default_user_message = "A messaging error occurred. Please try again."
