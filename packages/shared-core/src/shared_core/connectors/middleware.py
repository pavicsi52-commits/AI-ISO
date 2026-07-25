"""Execution middleware.

Per docs/027_Enterprise_Connector_SDK.md.txt "MIDDLEWARE": Authentication,
Retry, Telemetry, Audit, Metrics, Logging, Validation, Security. A
middleware chain generic over *any* connector operation (connect,
execute, discover, collect inventory, ...) rather than one method's
exact signature -- the same ``apply_middleware``/``_bind`` chain shape
as :mod:`shared_core.scheduler.middleware`/
:mod:`shared_core.notifications.middleware`, parameterized so it can
wrap ``connect()`` (returns ``None``), ``execute()`` (returns a
``CommandResult``), or any other operation identically.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

from opentelemetry.trace import Tracer

from shared_core.connectors import audit as connector_audit
from shared_core.connectors import metrics as connector_metrics
from shared_core.connectors.authentication import Authenticator, authenticate
from shared_core.connectors.connection import ConnectionConfig
from shared_core.connectors.credentials import Credential
from shared_core.connectors.retry import CircuitBreaker, connector_retry_policy
from shared_core.connectors.telemetry import trace_operation
from shared_core.connectors.validation import validate_connection_config
from shared_core.exceptions.authorization import AuthorizationError
from shared_core.logging.logger import get_logger
from shared_core.queue.retry import RetryPolicy

logger = get_logger("shared_core.connectors")

T = TypeVar("T")

_AUDIT_SUCCESS = "success"

_ATTEMPT_START = 1


@dataclass(frozen=True, slots=True)
class OperationContext:
    """Identifies one connector operation a middleware chain wraps."""

    provider: str
    target: str
    operation: str
    credential: Credential | None = None
    config: ConnectionConfig | None = None
    detail: str | None = None


Handler = Callable[[OperationContext], Awaitable[T]]
Middleware = Callable[[OperationContext, Handler[T]], Awaitable[T]]
PermissionChecker = Callable[[OperationContext], Awaitable[bool]]


def apply_middleware[T](handler: Handler[T], middlewares: list[Middleware[T]]) -> Handler[T]:
    """Wrap *handler* in every middleware, outermost first ("the chain")."""
    for middleware in reversed(middlewares):
        handler = _bind(middleware, handler)
    return handler


def _bind[T](middleware: Middleware[T], next_handler: Handler[T]) -> Handler[T]:
    async def wrapped(context: OperationContext) -> T:
        return await middleware(context, next_handler)

    return wrapped


async def logging_middleware[T](context: OperationContext, next_handler: Handler[T]) -> T:
    """Log the start and outcome of every operation ("Logging")."""
    logger.info(
        "Starting connector operation.",
        extra={
            "extra_fields": {
                "provider": context.provider,
                "target": context.target,
                "operation": context.operation,
            }
        },
    )
    try:
        result = await next_handler(context)
    except Exception:
        logger.exception("Connector operation failed.")
        raise
    logger.info(
        "Finished connector operation.",
        extra={"extra_fields": {"provider": context.provider, "operation": context.operation}},
    )
    return result


async def validation_middleware[T](context: OperationContext, next_handler: Handler[T]) -> T:
    """Validate the connection config, if given, before proceeding ("Validation")."""
    if context.config is not None:
        validate_connection_config(context.config)
    return await next_handler(context)


async def metrics_collection_middleware[T](
    context: OperationContext, next_handler: Handler[T]
) -> T:
    """Record every operation's outcome to Prometheus ("Metrics")."""
    start = time.perf_counter()
    try:
        result = await next_handler(context)
    except Exception:
        connector_metrics.record_failure(context.provider)
        raise
    connector_metrics.record_success(context.provider, latency_seconds=time.perf_counter() - start)
    return result


def _audit_success(context: OperationContext) -> None:
    if context.operation == "connect":
        connector_audit.audit_connect(context.provider, context.target)
    elif context.operation == "disconnect":
        connector_audit.audit_disconnect(context.provider, context.target)
    elif context.operation == "discover":
        connector_audit.audit_discovery(context.provider, context.target, outcome=_AUDIT_SUCCESS)
    elif context.operation == "collect_inventory":
        connector_audit.audit_inventory(context.provider, context.target, outcome=_AUDIT_SUCCESS)
    elif context.operation == "execute":
        connector_audit.audit_command(
            context.provider,
            context.target,
            command=context.detail or context.operation,
            outcome=_AUDIT_SUCCESS,
        )


async def audit_middleware[T](context: OperationContext, next_handler: Handler[T]) -> T:
    """Audit-log every operation's outcome ("Audit")."""
    try:
        result = await next_handler(context)
    except Exception as exc:
        connector_audit.audit_failure(
            context.provider, context.target, operation=context.operation, error=str(exc)
        )
        raise
    _audit_success(context)
    return result


def build_authentication_middleware[T](authenticator: Authenticator) -> Middleware[T]:
    """Build a middleware authenticating first, if given a credential ("Authentication")."""

    async def middleware(context: OperationContext, next_handler: Handler[T]) -> T:
        if context.credential is not None:
            await authenticate(context.credential, authenticator)
        return await next_handler(context)

    return middleware


def build_telemetry_middleware[T](tracer: Tracer) -> Middleware[T]:
    """Build a middleware wrapping every operation in a trace span ("Telemetry")."""

    async def middleware(context: OperationContext, next_handler: Handler[T]) -> T:
        async with trace_operation(
            tracer,
            context.provider,
            provider=context.provider,
            target=context.target,
            operation=context.operation,
        ):
            return await next_handler(context)

    return middleware


def build_retry_middleware[T](
    *, policy: RetryPolicy | None = None, circuit_breaker: CircuitBreaker | None = None
) -> Middleware[T]:
    """Build a middleware retrying a failed operation with backoff ("Retry")."""
    retry_policy = policy or connector_retry_policy()

    async def middleware(context: OperationContext, next_handler: Handler[T]) -> T:
        last_error: Exception = RuntimeError("Retry middleware ran zero attempts.")
        for attempt in range(_ATTEMPT_START, retry_policy.max_attempts + 1):
            if circuit_breaker is not None:
                circuit_breaker.before_call()
            try:
                result = await next_handler(context)
            except Exception as exc:
                last_error = exc
                if circuit_breaker is not None:
                    circuit_breaker.record_failure()
                is_final_attempt = attempt == retry_policy.max_attempts
                if not retry_policy.classify(exc) or is_final_attempt:
                    break
                connector_metrics.record_retry(context.provider)
                await asyncio.sleep(retry_policy.delay_for(attempt))
                continue
            if circuit_breaker is not None:
                circuit_breaker.record_success()
            return result
        raise last_error

    return middleware


def build_security_middleware[T](checker: PermissionChecker) -> Middleware[T]:
    """Build a middleware denying an operation unless *checker* approves ("Security")."""

    async def middleware(context: OperationContext, next_handler: Handler[T]) -> T:
        if not await checker(context):
            raise AuthorizationError(
                f"Operation {context.operation!r} denied for provider {context.provider!r}."
            )
        return await next_handler(context)

    return middleware


__all__ = [
    "Handler",
    "Middleware",
    "OperationContext",
    "PermissionChecker",
    "apply_middleware",
    "audit_middleware",
    "build_authentication_middleware",
    "build_retry_middleware",
    "build_security_middleware",
    "build_telemetry_middleware",
    "logging_middleware",
    "metrics_collection_middleware",
    "validation_middleware",
]
