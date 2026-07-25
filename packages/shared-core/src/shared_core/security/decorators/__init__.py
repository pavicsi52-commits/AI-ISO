"""Security decorators (docs/017 "SECURITY DECORATORS").

``requires_permission``/``requires_role``/``requires_organization``/
``requires_project`` already exist in
:mod:`shared_core.decorators.security` (Prompt 012) and are re-exported
here, not duplicated. ``requires_auth``, ``requires_api_key``, and
``requires_mfa`` are new.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any

from shared_core.decorators.security import (
    requires_organization,
    requires_permission,
    requires_project,
    requires_role,
)
from shared_core.exceptions.authentication import AuthenticationError
from shared_core.security.context import get_security_context

__all__ = [
    "requires_api_key",
    "requires_auth",
    "requires_mfa",
    "requires_organization",
    "requires_permission",
    "requires_project",
    "requires_role",
]


def requires_auth() -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
    """Require that a caller's identity was established (any authentication method)."""

    def decorator(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            if get_security_context().user_id is None:
                raise AuthenticationError("Authentication is required.")
            return await func(*args, **kwargs)

        return wrapper

    return decorator


def requires_api_key() -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
    """Require that the caller authenticated via an API key specifically."""

    def decorator(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            if get_security_context().auth_method != "api_key":
                raise AuthenticationError("This endpoint requires API key authentication.")
            return await func(*args, **kwargs)

        return wrapper

    return decorator


def requires_mfa() -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
    """Require that the caller completed multi-factor authentication."""

    def decorator(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not get_security_context().mfa_verified:
                raise AuthenticationError("Multi-factor authentication is required.")
            return await func(*args, **kwargs)

        return wrapper

    return decorator
