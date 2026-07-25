"""RBAC and tenant-scope decorators.

Read the caller's identity from :mod:`shared_core.security.context`, which
a service's authentication middleware populates after verifying a JWT.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any

from shared_core.enums.permission import Permission
from shared_core.enums.role import Role
from shared_core.exceptions.authorization import AuthorizationError
from shared_core.security.context import get_security_context
from shared_core.security.rbac import has_permission


def requires_permission(
    permission: Permission,
) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
    """Require the caller's role to grant ``permission``."""

    def decorator(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            context = get_security_context()
            if context.role is None or not has_permission(context.role, permission):
                raise AuthorizationError(f"Requires permission '{permission.value}'.")
            return await func(*args, **kwargs)

        return wrapper

    return decorator


def requires_role(
    role: Role,
) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
    """Require the caller to have exactly ``role`` (or ``SUPER_ADMIN``)."""

    def decorator(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            context = get_security_context()
            if context.role not in (role, Role.SUPER_ADMIN):
                raise AuthorizationError(f"Requires role '{role.value}'.")
            return await func(*args, **kwargs)

        return wrapper

    return decorator


def requires_organization() -> (
    Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]
):
    """Require the caller's request to carry an organization scope."""

    def decorator(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            if get_security_context().organization_id is None:
                raise AuthorizationError("Requires an organization scope.")
            return await func(*args, **kwargs)

        return wrapper

    return decorator


def requires_project() -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
    """Require the caller's request to carry a project scope."""

    def decorator(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            if get_security_context().project_id is None:
                raise AuthorizationError("Requires a project scope.")
            return await func(*args, **kwargs)

        return wrapper

    return decorator
