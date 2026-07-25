"""Asset inventory exception."""

from __future__ import annotations

from shared_core.exceptions.base import AIIOSException


class InventoryError(AIIOSException):
    """Raised when an asset inventory operation (scan, discovery, sync) fails."""

    error_code = "AIIOS-INVENTORY-0001"
    status_code = 500
    severity = "medium"
    retryable = False
    default_user_message = "An inventory error occurred. Please try again."
