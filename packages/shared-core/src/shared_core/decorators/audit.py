"""Audit logging decorator."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any

from shared_core.enums.audit_action import AuditAction
from shared_core.helpers.time_helper import Stopwatch
from shared_core.logging.logger import get_logger
from shared_core.security.context import get_security_context

logger = get_logger("shared_core.audit")


def audit(
    action: AuditAction,
) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
    """Log an audit entry recording who performed ``action`` and its outcome."""

    def decorator(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            context = get_security_context()
            stopwatch = Stopwatch()
            try:
                result = await func(*args, **kwargs)
            except Exception:
                logger.info(
                    "audit",
                    extra={
                        "extra_fields": {
                            "action": action.value,
                            "user_id": str(context.user_id) if context.user_id else None,
                            "organization_id": (
                                str(context.organization_id) if context.organization_id else None
                            ),
                            "result": "failure",
                            "duration_ms": stopwatch.elapsed_ms(),
                        }
                    },
                )
                raise
            logger.info(
                "audit",
                extra={
                    "extra_fields": {
                        "action": action.value,
                        "user_id": str(context.user_id) if context.user_id else None,
                        "organization_id": (
                            str(context.organization_id) if context.organization_id else None
                        ),
                        "result": "success",
                        "duration_ms": stopwatch.elapsed_ms(),
                    }
                },
            )
            return result

        return wrapper

    return decorator
