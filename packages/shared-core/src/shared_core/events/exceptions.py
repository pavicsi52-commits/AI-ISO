"""Event-framework-specific exceptions.

Each subclasses :class:`shared_core.exceptions.event.EventError` so a bare
``except EventError`` still catches everything raised anywhere in this
framework. Not registered in :mod:`shared_core.exceptions.constants`'s
central catalog -- same reasoning as
:mod:`shared_core.database.exceptions`/:mod:`shared_core.cache.exceptions`:
that module already depends on :mod:`shared_core.exceptions.event`, so
importing back from here would cycle. Error codes are manually kept
unique in the ``AIIOS-EVENT-*`` range against the base class's
``AIIOS-EVENT-0001``.
"""

from __future__ import annotations

from shared_core.exceptions.event import EventError


class EventValidationError(EventError):
    """Raised when an event fails schema/version/payload/metadata/tenant/permission validation."""

    error_code = "AIIOS-EVENT-0002"
    status_code = 400
    retryable = False
    default_user_message = "The event is invalid."


class EventVersionMismatchError(EventError):
    """Raised when an event's version isn't supported, or no migration path exists to it."""

    error_code = "AIIOS-EVENT-0003"
    status_code = 400
    retryable = False
    default_user_message = "The event version is not supported."


class EventPublishFailedError(EventError):
    """Raised when publishing an event to the broker fails."""

    error_code = "AIIOS-EVENT-0004"
    status_code = 503
    retryable = True
    default_user_message = "The event could not be published. Please try again."


class EventConsumeFailedError(EventError):
    """Raised when a subscriber's handler fails processing an event."""

    error_code = "AIIOS-EVENT-0005"
    status_code = 500
    retryable = True
    default_user_message = "The event could not be processed."


class EventReplayError(EventError):
    """Raised when replaying events (by criteria, or from the dead-letter queue) fails."""

    error_code = "AIIOS-EVENT-0006"
    status_code = 500
    retryable = False
    default_user_message = "The event replay could not be completed."


class DeadLetterError(EventError):
    """Raised when inspecting, replaying, or purging a dead-letter queue fails."""

    error_code = "AIIOS-EVENT-0007"
    status_code = 500
    retryable = False
    default_user_message = "The dead-letter operation could not be completed."


class EventRegistrationError(EventError):
    """Raised when registering an event class with the registry fails (e.g. a name clash)."""

    error_code = "AIIOS-EVENT-0008"
    status_code = 500
    retryable = False
    default_user_message = "The event could not be registered."


class SubscriberError(EventError):
    """Raised when subscribing to, or unsubscribing from, an event fails."""

    error_code = "AIIOS-EVENT-0009"
    status_code = 500
    retryable = False
    default_user_message = "The subscription could not be completed."


__all__ = [
    "DeadLetterError",
    "EventConsumeFailedError",
    "EventPublishFailedError",
    "EventRegistrationError",
    "EventReplayError",
    "EventValidationError",
    "EventVersionMismatchError",
    "SubscriberError",
]
