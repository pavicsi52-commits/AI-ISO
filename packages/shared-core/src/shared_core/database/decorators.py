"""Cross-cutting database decorators.

Per docs/018_Enterprise_Database_Framework.md.txt "DECORATORS": ``@transaction``,
``@readonly``, ``@tenant``, ``@audit``, ``@soft_delete``, ``@retry``.
``@transaction`` and ``@audit`` re-export Prompt 012's
:mod:`shared_core.decorators` implementations (transaction wrapping and
audit logging aren't database-specific concerns) rather than duplicating
them under a new name; the other four are genuinely new here.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, TypeVar
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from shared_core.database.constants import (
    DEFAULT_TRANSACTION_BACKOFF_BASE_SECONDS,
    DEFAULT_TRANSACTION_BACKOFF_MAX_SECONDS,
    DEFAULT_TRANSACTION_MAX_ATTEMPTS,
)
from shared_core.database.exceptions import TenantViolationError, TransactionFailedError
from shared_core.database.soft_delete import mark_deleted
from shared_core.database.transaction import is_retryable_error
from shared_core.decorators.audit import audit
from shared_core.decorators.transaction import transactional as transaction
from shared_core.enums.role import Role
from shared_core.security.context import get_security_context

_F = TypeVar("_F", bound=Callable[..., Awaitable[Any]])


def _extract_session(args: tuple[Any, ...], kwargs: dict[str, Any], func_name: str) -> AsyncSession:
    session = kwargs.get("session") or next(
        (arg for arg in args if isinstance(arg, AsyncSession)), None
    )
    if session is None:
        raise TypeError(
            f"{func_name} must receive an AsyncSession positional argument or "
            "'session' keyword argument."
        )
    return session


def readonly[F: Callable[..., Awaitable[Any]]](func: F) -> F:
    """Guarantee the decorated function's session performs no durable writes.

    Rolls back unconditionally after the call, success or failure -- for
    callers that need a read-only *guarantee*, not just an intent comment,
    even if the function accidentally calls ``session.add()``.
    """

    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        session = _extract_session(args, kwargs, func.__name__)
        try:
            return await func(*args, **kwargs)
        finally:
            await session.rollback()

    return wrapper  # type: ignore[return-value]


def tenant(*, organization_id_param: str = "organization_id") -> Callable[[_F], _F]:
    """Enforce the decorated function is only called within the caller's own tenant.

    Compares the *organization_id_param* keyword argument against
    :func:`~shared_core.security.context.get_security_context`'s
    ``organization_id``; a super admin bypasses the check
    (docs/018 "TENANT ISOLATION": "No bypass unless Super Admin").
    """

    def decorator(func: _F) -> _F:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            context = get_security_context()
            if context.role == Role.SUPER_ADMIN:
                return await func(*args, **kwargs)

            called_organization_id = kwargs.get(organization_id_param)
            if called_organization_id is None:
                raise TenantViolationError(
                    f"{func.__name__} requires '{organization_id_param}' for tenant enforcement."
                )
            if context.organization_id != called_organization_id:
                raise TenantViolationError(
                    f"{func.__name__} was called for an organization other than the caller's own."
                )
            return await func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


def soft_delete(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    """Force the entity returned by the decorated function through soft-delete semantics.

    Whatever the wrapped function's own delete logic did (or forgot to do),
    the returned entity's ``deleted_at``/``deleted_by``/``is_active``
    columns are set correctly on the way out -- a custom delete-like method
    can never accidentally perform a hard delete or half-apply the fields.
    """

    @wraps(func)
    async def wrapper(*args: Any, deleted_by: UUID | None = None, **kwargs: Any) -> Any:
        entity = await func(*args, deleted_by=deleted_by, **kwargs)
        mark_deleted(entity, deleted_by=deleted_by)
        return entity

    return wrapper


def retry(
    *,
    max_attempts: int = DEFAULT_TRANSACTION_MAX_ATTEMPTS,
    backoff_base_seconds: float = DEFAULT_TRANSACTION_BACKOFF_BASE_SECONDS,
    backoff_max_seconds: float = DEFAULT_TRANSACTION_BACKOFF_MAX_SECONDS,
) -> Callable[[_F], _F]:
    """Retry the decorated function with exponential backoff on retryable DB errors.

    Only deadlocks, serialization failures, and transient connection drops
    are retried (:func:`shared_core.database.transaction.is_retryable_error`)
    -- anything else propagates immediately.
    """

    def decorator(func: _F) -> _F:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_error: BaseException | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except SQLAlchemyError as exc:
                    if not is_retryable_error(exc) or attempt == max_attempts:
                        raise
                    last_error = exc
                    delay = min(backoff_base_seconds * (2 ** (attempt - 1)), backoff_max_seconds)
                    delay += random.uniform(0, backoff_base_seconds)
                    await asyncio.sleep(delay)
            raise TransactionFailedError(
                "Retry loop exited unexpectedly."
            ) from last_error  # pragma: no cover -- loop always returns or raises above

        return wrapper  # type: ignore[return-value]

    return decorator


__all__ = ["audit", "readonly", "retry", "soft_delete", "tenant", "transaction"]
