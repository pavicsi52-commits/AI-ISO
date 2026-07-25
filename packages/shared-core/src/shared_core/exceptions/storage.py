"""Object storage exception."""

from __future__ import annotations

from shared_core.exceptions.base import AIIOSException


class StorageError(AIIOSException):
    """Raised when an object storage operation fails (MinIO/S3-compatible).

    Per docs/015 "RETRY POLICY": storage failures are retryable.
    """

    error_code = "AIIOS-STORAGE-0001"
    status_code = 503
    severity = "high"
    retryable = True
    default_user_message = "A storage error occurred. Please try again."
