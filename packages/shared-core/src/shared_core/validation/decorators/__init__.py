"""Validation decorators (docs/016 "DECORATORS").

Each decorator runs a validation rule before the wrapped function executes
and raises the matching :mod:`shared_core.exceptions` type on failure --
per docs/016 "ERROR FORMAT": "Use Prompt 006. Never invent custom
validation responses." All six share one small factory rather than each
reimplementing "run the rule, raise on failure, else proceed"
("No validation logic shall be duplicated").
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any

from shared_core.exceptions.authorization import AuthorizationError
from shared_core.exceptions.base import AIIOSException
from shared_core.exceptions.business import BusinessRuleError
from shared_core.exceptions.database import DatabaseError
from shared_core.exceptions.validation import ValidationError
from shared_core.exceptions.workflow import WorkflowError
from shared_core.validation.results import ValidationResult


def _make_validation_decorator(
    exception_cls: type[AIIOSException],
) -> Callable[..., Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]]:
    def decorator_factory(
        rule: Callable[..., ValidationResult], *rule_args: Any, **rule_kwargs: Any
    ) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
        def decorator(
            wrapped: Callable[..., Awaitable[Any]],
        ) -> Callable[..., Awaitable[Any]]:
            @wraps(wrapped)
            async def wrapper(*args: Any, **kwargs: Any) -> Any:
                result = rule(*rule_args, **rule_kwargs)
                if not result.valid:
                    raise exception_cls("Validation failed.", details=result.errors)
                return await wrapped(*args, **kwargs)

            return wrapper

        return decorator

    return decorator_factory


validate_request = _make_validation_decorator(ValidationError)
"""Run a request-validation rule (headers/query/body/...) before the handler."""

validate_response = _make_validation_decorator(ValidationError)
"""Run a response-envelope-compliance rule before returning a response."""

validate_permission = _make_validation_decorator(AuthorizationError)
"""Run a permission/RBAC rule before the handler."""

validate_business = _make_validation_decorator(BusinessRuleError)
"""Run a business rule (quota, ownership, uniqueness, ...) before the handler."""

validate_workflow = _make_validation_decorator(WorkflowError)
"""Run a workflow-graph rule before the handler."""

validate_database = _make_validation_decorator(DatabaseError)
"""Run a database rule (foreign key, version, tenant isolation, ...) before the handler."""
