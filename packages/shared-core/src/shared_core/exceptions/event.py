"""Event framework exception."""

from __future__ import annotations

from shared_core.exceptions.base import AIIOSException


class EventError(AIIOSException):
    """Raised when publishing, consuming, or processing an event fails
    (docs/020_Enterprise_Event_Framework.md.txt). Not retryable by
    default -- a malformed or unprocessable event payload will fail the
    same way on retry; the event framework's own replay mechanism (not a
    blind retry) is the correct recovery path.
    """

    error_code = "AIIOS-EVENT-0001"
    status_code = 500
    severity = "high"
    retryable = False
    default_user_message = "An error occurred while processing this event."
