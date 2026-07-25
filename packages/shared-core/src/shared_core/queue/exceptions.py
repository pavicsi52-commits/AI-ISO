"""Queue-framework-specific exceptions.

Each subclasses :class:`shared_core.exceptions.queue.QueueError` so a bare
``except QueueError`` still catches everything raised anywhere in this
framework. Not registered in :mod:`shared_core.exceptions.constants`'s
central catalog -- same reasoning as
:mod:`shared_core.database.exceptions`/:mod:`shared_core.cache.exceptions`/
:mod:`shared_core.events.exceptions`: that module already depends on
:mod:`shared_core.exceptions.queue`, so importing back from here would
cycle. Error codes are manually kept unique in the ``AIIOS-QUEUE-*``
range against the base class's ``AIIOS-QUEUE-0001``.
"""

from __future__ import annotations

from shared_core.exceptions.queue import QueueError


class ConnectionFailedError(QueueError):
    """Raised when a broker connection can't be established after every retry attempt."""

    error_code = "AIIOS-QUEUE-0002"
    status_code = 503
    retryable = True
    default_user_message = "Could not connect to the message broker. Please try again."


class PublishFailedError(QueueError):
    """Raised when publishing a message fails after every retry attempt."""

    error_code = "AIIOS-QUEUE-0003"
    status_code = 503
    retryable = True
    default_user_message = "The message could not be published. Please try again."


class ConsumeFailedError(QueueError):
    """Raised when a consumer's handler fails processing a message."""

    error_code = "AIIOS-QUEUE-0004"
    status_code = 500
    retryable = True
    default_user_message = "The message could not be processed."


class DeadLetterError(QueueError):
    """Raised when a dead-letter inspect/replay/filter/export/purge operation fails."""

    error_code = "AIIOS-QUEUE-0005"
    status_code = 500
    retryable = False
    default_user_message = "The dead-letter operation could not be completed."


class SchedulingError(QueueError):
    """Raised when scheduling, rescheduling, or cancelling a task fails."""

    error_code = "AIIOS-QUEUE-0006"
    status_code = 500
    retryable = False
    default_user_message = "The task could not be scheduled."


class WorkerPoolError(QueueError):
    """Raised when starting, stopping, or scaling a worker pool fails."""

    error_code = "AIIOS-QUEUE-0007"
    status_code = 500
    retryable = False
    default_user_message = "The worker pool operation could not be completed."


class InvalidPriorityError(QueueError):
    """Raised when a priority level isn't one of the framework's five supported levels."""

    error_code = "AIIOS-QUEUE-0008"
    status_code = 400
    retryable = False
    default_user_message = "The requested priority level is invalid."


class InvalidDelayError(QueueError):
    """Raised when a requested delay is negative or exceeds the maximum supported delay."""

    error_code = "AIIOS-QUEUE-0009"
    status_code = 400
    retryable = False
    default_user_message = "The requested delay is invalid."


class RoutingError(QueueError):
    """Raised when declaring an exchange, binding, or resolving a routing key fails."""

    error_code = "AIIOS-QUEUE-0010"
    status_code = 500
    retryable = False
    default_user_message = "The message could not be routed."


__all__ = [
    "ConnectionFailedError",
    "ConsumeFailedError",
    "DeadLetterError",
    "InvalidDelayError",
    "InvalidPriorityError",
    "PublishFailedError",
    "RoutingError",
    "SchedulingError",
    "WorkerPoolError",
]
