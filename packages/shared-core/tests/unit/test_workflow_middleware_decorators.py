"""Tests for middleware.py and decorators.py."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest
from shared_core.exceptions.authorization import AuthorizationError
from shared_core.workflow.decorators import get_node_type, node_handler, retryable, timed
from shared_core.workflow.exceptions import ExpressionEvaluationError
from shared_core.workflow.middleware import (
    WorkflowOperationContext,
    apply_middleware,
    audit_privileged_middleware,
    build_rbac_middleware,
    build_tenant_isolation_middleware,
    logging_middleware,
)
from shared_core.workflow.nodes import NodeType

# --- middleware.py ---


def _context(**overrides: object) -> WorkflowOperationContext:
    defaults: dict[str, object] = {
        "workflow_id": "wf-1",
        "execution_id": "exec-1",
        "operation": "run",
    }
    defaults.update(overrides)
    return WorkflowOperationContext(**defaults)  # type: ignore[arg-type]


async def test_apply_middleware_runs_in_outermost_first_order() -> None:
    calls: list[str] = []

    def make(
        name: str,
    ) -> Callable[
        [WorkflowOperationContext, Callable[[WorkflowOperationContext], Awaitable[str]]],
        Awaitable[str],
    ]:
        async def middleware(
            context: WorkflowOperationContext,
            next_handler: Callable[[WorkflowOperationContext], Awaitable[str]],
        ) -> str:
            calls.append(f"{name}-before")
            result = await next_handler(context)
            calls.append(f"{name}-after")
            return result

        return middleware

    outer = make("outer")
    inner = make("inner")

    async def handler(_context: WorkflowOperationContext) -> str:
        calls.append("handler")
        return "done"

    wrapped = apply_middleware(handler, [outer, inner])
    result = await wrapped(_context())

    assert result == "done"
    assert calls == ["outer-before", "inner-before", "handler", "inner-after", "outer-after"]


async def test_apply_middleware_with_no_middlewares_calls_handler_directly() -> None:
    async def handler(_context: WorkflowOperationContext) -> str:
        return "direct"

    wrapped = apply_middleware(handler, [])

    assert await wrapped(_context()) == "direct"


async def test_logging_middleware_passes_through_on_success() -> None:
    async def handler(_context: WorkflowOperationContext) -> str:
        return "ok"

    wrapped = apply_middleware(handler, [logging_middleware])

    assert await wrapped(_context()) == "ok"


async def test_logging_middleware_reraises_on_failure() -> None:
    async def handler(_context: WorkflowOperationContext) -> str:
        raise RuntimeError("boom")

    wrapped = apply_middleware(handler, [logging_middleware])

    with pytest.raises(RuntimeError, match="boom"):
        await wrapped(_context())


async def test_rbac_middleware_allows_when_checker_approves() -> None:
    async def checker(_context: WorkflowOperationContext) -> bool:
        return True

    async def handler(_context: WorkflowOperationContext) -> str:
        return "allowed"

    wrapped = apply_middleware(handler, [build_rbac_middleware(checker)])

    assert await wrapped(_context()) == "allowed"


async def test_rbac_middleware_denies_when_checker_rejects() -> None:
    async def checker(_context: WorkflowOperationContext) -> bool:
        return False

    async def handler(_context: WorkflowOperationContext) -> str:
        return "unreachable"

    wrapped = apply_middleware(handler, [build_rbac_middleware(checker)])

    with pytest.raises(AuthorizationError):
        await wrapped(_context())


async def test_tenant_isolation_middleware_allows_matching_org() -> None:
    async def handler(_context: WorkflowOperationContext) -> str:
        return "ok"

    wrapped = apply_middleware(handler, [build_tenant_isolation_middleware("org-1")])

    result = await wrapped(_context(organization_id="org-1"))

    assert result == "ok"


async def test_tenant_isolation_middleware_allows_when_context_has_no_org() -> None:
    async def handler(_context: WorkflowOperationContext) -> str:
        return "ok"

    wrapped = apply_middleware(handler, [build_tenant_isolation_middleware("org-1")])

    assert await wrapped(_context()) == "ok"


async def test_tenant_isolation_middleware_denies_mismatched_org() -> None:
    async def handler(_context: WorkflowOperationContext) -> str:
        return "unreachable"

    wrapped = apply_middleware(handler, [build_tenant_isolation_middleware("org-1")])

    with pytest.raises(AuthorizationError):
        await wrapped(_context(organization_id="org-2"))


async def test_audit_privileged_middleware_runs_for_privileged_operation() -> None:
    async def handler(_context: WorkflowOperationContext) -> str:
        return "ok"

    wrapped = apply_middleware(handler, [audit_privileged_middleware])

    result = await wrapped(_context(privileged=True, user_id="user-1"))

    assert result == "ok"


async def test_audit_privileged_middleware_is_a_no_op_for_non_privileged_operation() -> None:
    async def handler(_context: WorkflowOperationContext) -> str:
        return "ok"

    wrapped = apply_middleware(handler, [audit_privileged_middleware])

    assert await wrapped(_context(privileged=False)) == "ok"


# --- decorators.py ---


def test_node_handler_marks_the_function() -> None:
    @node_handler(NodeType.TASK)
    async def handler() -> None:
        return None

    assert get_node_type(handler) is NodeType.TASK


def test_get_node_type_returns_none_when_unmarked() -> None:
    async def handler() -> None:
        return None

    assert get_node_type(handler) is None


async def test_retryable_retries_until_success() -> None:
    attempts = 0

    @retryable(max_attempts=3)
    async def flaky() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            raise ConnectionError("transient")
        return "ok"

    result = await flaky()

    assert result == "ok"
    assert attempts == 2


async def test_retryable_raises_after_exhausting_attempts() -> None:
    attempts = 0

    @retryable(max_attempts=2)
    async def always_fails() -> None:
        nonlocal attempts
        attempts += 1
        raise ConnectionError("persistent")

    with pytest.raises(ConnectionError, match="persistent"):
        await always_fails()

    assert attempts == 2


async def test_retryable_does_not_retry_a_non_retryable_error() -> None:
    attempts = 0

    @retryable(max_attempts=3)
    async def fails_fast() -> None:
        nonlocal attempts
        attempts += 1
        raise ExpressionEvaluationError("not retryable")

    with pytest.raises(ExpressionEvaluationError, match="not retryable"):
        await fails_fast()

    assert attempts == 1


async def test_timed_returns_the_wrapped_result() -> None:
    @timed("wf-1", "task")
    async def handler() -> str:
        return "value"

    assert await handler() == "value"


async def test_timed_reraises_on_failure() -> None:
    @timed("wf-1", "task")
    async def handler() -> None:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        await handler()
