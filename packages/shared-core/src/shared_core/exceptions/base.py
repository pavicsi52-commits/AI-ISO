"""Base exception every AI-IOS custom exception inherits.

Expanded per docs/015_Enterprise_Exception_Framework.md.txt: a global
FastAPI handler (``handlers.py``), automatic mapping from third-party
exceptions (``mapper.py``), a code-driven factory (``factory.py``), and a
full error-code catalog with localization (``constants.py``).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID


class AIIOSException(Exception):  # noqa: N818 -- name mandated verbatim by the spec
    """Base class for every exception raised by AI-IOS platform code.

    Attributes:
        message: Internal diagnostic message. May contain detail unsafe to
            return to an API client (see docs/015 "SECURITY": never expose
            SQL errors, tracebacks, or secrets). Logged, never serialized
            into an API response.
        user_message: Safe, localizable, user-facing message. What
            ``handlers.py`` actually puts in the API response
            (docs/015 "LOCALIZATION": "Store user-facing messages
            separately from internal diagnostic messages"). Defaults to
            the subclass's :attr:`default_user_message` when not given
            explicitly.
        error_code: Stable machine-readable code, ``AIIOS-<DOMAIN>-<NUMBER>``.
        status_code: HTTP status code this exception maps to.
        severity: One of ``"low"``, ``"medium"``, ``"high"``, ``"critical"``.
        retryable: Whether the caller may safely retry the operation.
        details: Additional structured error details (e.g. field errors).
            Client-visible -- never put internal diagnostic detail here.
        metadata: Arbitrary diagnostic metadata, never sent to API clients.
        timestamp: When the exception was constructed, UTC.
        request_id: Request ID in scope when the exception was raised, if any.
        correlation_id: Correlation ID in scope when raised, if any.
        organization_id: Organization ID in scope when raised, if any.
        project_id: Project ID in scope when raised, if any.
    """

    error_code: str = "AIIOS-CORE-0000"
    status_code: int = 500
    severity: str = "medium"
    retryable: bool = False
    default_user_message: str = "An unexpected error occurred. Please try again."

    def __init__(
        self,
        message: str,
        *,
        user_message: str | None = None,
        details: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        request_id: str | None = None,
        correlation_id: str | None = None,
        organization_id: UUID | None = None,
        project_id: UUID | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.user_message = user_message or self.default_user_message
        self.details = details or []
        self.metadata = metadata or {}
        self.timestamp = datetime.now(UTC)
        self.request_id = request_id
        self.correlation_id = correlation_id
        self.organization_id = organization_id
        self.project_id = project_id

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dict suitable for structured logging.

        Includes the internal diagnostic ``message`` -- for logs only,
        never for an API response. See :meth:`to_public_dict`.
        """
        return {
            "error_code": self.error_code,
            "message": self.message,
            "user_message": self.user_message,
            "status_code": self.status_code,
            "severity": self.severity,
            "retryable": self.retryable,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
            "request_id": self.request_id,
            "correlation_id": self.correlation_id,
            "organization_id": str(self.organization_id) if self.organization_id else None,
            "project_id": str(self.project_id) if self.project_id else None,
        }

    def to_public_dict(self) -> dict[str, Any]:
        """Serialize to the subset of fields safe to return to an API client.

        Never includes the internal diagnostic ``message``, ``metadata``,
        or a stack trace -- only the error code, the (localizable)
        ``user_message``, and ``details``.
        """
        return {
            "error_code": self.error_code,
            "user_message": self.user_message,
            "details": self.details,
        }
