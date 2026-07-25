"""Plugin exception."""

from __future__ import annotations

from shared_core.exceptions.base import AIIOSException


class PluginError(AIIOSException):
    """Raised when a plugin operation fails (install, load, enable, execute,
    validate, or resolve dependencies for)."""

    error_code = "AIIOS-PLUGIN-0001"
    status_code = 502
    severity = "medium"
    retryable = False
    default_user_message = "The plugin operation could not be completed."
