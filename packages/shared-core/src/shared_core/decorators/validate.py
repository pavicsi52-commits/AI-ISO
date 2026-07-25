"""Validation decorator."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any

from shared_core.exceptions.validation import ValidationError
from shared_core.validators.results import ValidationResult


def validates(
    argument_name: str, validator: Callable[[Any], ValidationResult]
) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
    """Validate the named keyword argument with ``validator`` before calling.

    Raises:
        ValidationError: If the validator reports the value as invalid.
    """

    def decorator(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            if argument_name in kwargs:
                result = validator(kwargs[argument_name])
                if not result.valid:
                    raise ValidationError(
                        f"Validation failed for '{argument_name}'.", details=result.errors
                    )
            return await func(*args, **kwargs)

        return wrapper

    return decorator
