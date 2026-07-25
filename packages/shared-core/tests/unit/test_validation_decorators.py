"""Tests for validation decorators."""

from __future__ import annotations

import pytest
from shared_core.exceptions import (
    AuthorizationError,
    BusinessRuleError,
    DatabaseError,
    ValidationError,
)
from shared_core.exceptions.workflow import WorkflowError
from shared_core.validation.decorators import (
    validate_business,
    validate_database,
    validate_permission,
    validate_request,
    validate_response,
    validate_workflow,
)
from shared_core.validation.results import ValidationResult


def _ok(*args: object, **kwargs: object) -> ValidationResult:
    return ValidationResult.ok()


def _fail(*args: object, **kwargs: object) -> ValidationResult:
    return ValidationResult.fail("nope")


async def test_validate_request_allows_when_rule_passes() -> None:
    @validate_request(_ok)
    async def handler() -> str:
        return "ok"

    assert await handler() == "ok"


async def test_validate_request_raises_validation_error_when_rule_fails() -> None:
    @validate_request(_fail)
    async def handler() -> str:
        return "ok"

    with pytest.raises(ValidationError):
        await handler()


async def test_validate_response_raises_validation_error() -> None:
    @validate_response(_fail)
    async def handler() -> str:
        return "ok"

    with pytest.raises(ValidationError):
        await handler()


async def test_validate_permission_raises_authorization_error() -> None:
    @validate_permission(_fail)
    async def handler() -> str:
        return "ok"

    with pytest.raises(AuthorizationError):
        await handler()


async def test_validate_business_raises_business_rule_error() -> None:
    @validate_business(_fail)
    async def handler() -> str:
        return "ok"

    with pytest.raises(BusinessRuleError):
        await handler()


async def test_validate_workflow_raises_workflow_error() -> None:
    @validate_workflow(_fail)
    async def handler() -> str:
        return "ok"

    with pytest.raises(WorkflowError):
        await handler()


async def test_validate_database_raises_database_error() -> None:
    @validate_database(_fail)
    async def handler() -> str:
        return "ok"

    with pytest.raises(DatabaseError):
        await handler()


async def test_decorator_passes_rule_args_and_kwargs() -> None:
    def rule(value: str, *, expected: str) -> ValidationResult:
        return ValidationResult.ok() if value == expected else ValidationResult.fail("mismatch")

    @validate_request(rule, "x", expected="x")
    async def handler() -> str:
        return "passed"

    assert await handler() == "passed"


async def test_decorator_preserves_wrapped_function_arguments() -> None:
    @validate_request(_ok)
    async def handler(value: int, *, extra: int = 0) -> int:
        return value + extra

    assert await handler(5, extra=2) == 7


async def test_failed_validation_carries_errors_as_details() -> None:
    @validate_request(_fail)
    async def handler() -> str:
        return "ok"

    with pytest.raises(ValidationError) as exc_info:
        await handler()

    assert exc_info.value.details == ["nope"]


async def test_decorator_preserves_function_metadata() -> None:
    @validate_request(_ok)
    async def my_named_handler() -> str:
        """A docstring."""
        return "ok"

    assert my_named_handler.__name__ == "my_named_handler"
    assert my_named_handler.__doc__ == "A docstring."
