"""Global FastAPI exception handler.

Per docs/015_Enterprise_Exception_Framework.md.txt "GLOBAL EXCEPTION
HANDLER": every FastAPI service registers this one centralized handler set
at startup; no controller-level exception handling. Every AI-IOS service
calls :func:`register_exception_handlers` -- none defines its own.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from shared_core.exceptions.authentication import AuthenticationError
from shared_core.exceptions.authorization import AuthorizationError
from shared_core.exceptions.base import AIIOSException
from shared_core.exceptions.business import BusinessRuleError
from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.constants import localize_message
from shared_core.exceptions.mapper import map_exception
from shared_core.exceptions.not_found import NotFoundError
from shared_core.exceptions.rate_limit import RateLimitError
from shared_core.exceptions.service import InternalError, UnknownError
from shared_core.exceptions.validation import ValidationError
from shared_core.logging.context import get_log_context
from shared_core.logging.filters import mask_text
from shared_core.logging.logger import get_logger
from shared_core.responses.error import ErrorDetail, ErrorResponse
from shared_core.schemas.meta import ResponseMeta

logger = get_logger("shared_core.exceptions")

_STATUS_CODE_TO_EXCEPTION: dict[int, type[AIIOSException]] = {
    400: ValidationError,
    401: AuthenticationError,
    403: AuthorizationError,
    404: NotFoundError,
    409: ConflictError,
    422: BusinessRuleError,
    429: RateLimitError,
    500: InternalError,
}
_SERVER_ERROR_THRESHOLD = 500


def register_exception_handlers(app: FastAPI) -> None:
    """Register the global exception handlers every AI-IOS FastAPI service uses."""

    @app.exception_handler(AIIOSException)
    async def handle_aiios_exception(request: Request, exc: AIIOSException) -> JSONResponse:
        return _respond(request, exc)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = [
            f"{'.'.join(str(part) for part in err['loc'])}: {err['msg']}" for err in exc.errors()
        ]
        mapped = ValidationError("Request validation failed.", details=details)
        return _respond(request, mapped, original=exc)

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        # A Starlette/FastAPI HTTPException (e.g. 404 for an undefined
        # route, or an explicit `raise HTTPException(status_code=...)`)
        # carries an intentional status code -- map by *that*, not by
        # exception type, so a 404 becomes NotFoundError, a 401 becomes
        # AuthenticationError, and so on.
        exception_cls = _STATUS_CODE_TO_EXCEPTION.get(
            exc.status_code,
            InternalError if exc.status_code >= _SERVER_ERROR_THRESHOLD else UnknownError,
        )
        mapped = exception_cls(exc.detail or exception_cls.__name__)
        mapped.status_code = exc.status_code
        return _respond(request, mapped, original=exc)

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        mapped = map_exception(exc)
        return _respond(request, mapped, original=exc)


def _respond(
    request: Request, exc: AIIOSException, *, original: Exception | None = None
) -> JSONResponse:
    """Log the exception, then build the Prompt 006 error envelope.

    Per docs/015 "SECURITY" and "API RESPONSE": never expose the internal
    diagnostic ``message``, a traceback, or a raw SQL error -- only the
    localized ``user_message`` and client-safe ``details``, both masked
    defensively in case a caller ever populated them with something
    sensitive.
    """
    _log_exception(exc, original=original)

    locale = getattr(request.state, "locale", "en")
    user_message = mask_text(localize_message(exc.error_code, locale, exc.user_message))
    details = [mask_text(detail) for detail in exc.details]

    context = get_log_context()
    body = ErrorResponse(
        message=user_message,
        error=ErrorDetail(code=exc.error_code, details=details),
        meta=ResponseMeta(request_id=context.request_id or "unknown"),
    )
    return JSONResponse(status_code=exc.status_code, content=body.model_dump(mode="json"))


def _log_exception(exc: AIIOSException, *, original: Exception | None = None) -> None:
    """Log every field docs/015 "LOGGING" requires.

    Request ID, correlation ID, service, and environment are already
    attached to every log line by
    :func:`shared_core.logging.formatter.build_log_record`; this adds the
    fields specific to an exception (type, severity, user/org/project) and
    the stack trace.
    """
    context = get_log_context()
    extra_fields: dict[str, Any] = {
        "error_code": exc.error_code,
        "exception_type": type(original if original is not None else exc).__name__,
        "severity": exc.severity,
        "retryable": exc.retryable,
        "user_id": context.user_id,
        "organization_id": context.organization_id,
        "project_id": context.project_id,
    }
    log_call = logger.critical if exc.severity == "critical" else logger.error
    log_call(exc.message, extra={"extra_fields": extra_fields}, exc_info=original or exc)
