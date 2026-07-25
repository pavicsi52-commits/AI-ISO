"""AI subsystem exception."""

from __future__ import annotations

from shared_core.exceptions.base import AIIOSException


class AIError(AIIOSException):
    """Raised when the AI assistant subsystem fails (model call, embedding,
    conversation persistence)."""

    error_code = "AIIOS-AI-0001"
    status_code = 502
    severity = "medium"
    retryable = True
    default_user_message = "The AI assistant is temporarily unavailable. Please try again."
