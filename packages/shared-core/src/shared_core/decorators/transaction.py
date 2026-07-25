"""Transaction decorator.

Wraps an async method so it runs inside a single atomic
:func:`shared_core.database.unit_of_work`. The decorated function's first
positional argument (after ``self``, if any) or a ``session`` keyword
argument must be the :class:`AsyncSession` to run within.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from shared_core.database.transaction import unit_of_work


def transactional(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    """Run the decorated async function inside a single atomic transaction."""

    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        session = kwargs.get("session") or next(
            (arg for arg in args if isinstance(arg, AsyncSession)), None
        )
        if session is None:
            raise TypeError(
                f"{func.__name__} decorated with @transactional must receive an "
                "AsyncSession positional argument or 'session' keyword argument."
            )
        async with unit_of_work(session):
            return await func(*args, **kwargs)

    return wrapper
