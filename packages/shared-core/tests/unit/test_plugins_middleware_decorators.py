"""Tests for middleware.py and decorators.py."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

import pytest
from shared_core.plugins.decorators import (
    extension,
    get_extension_target,
    get_hook_name,
    hook,
    retryable,
    timed,
)
from shared_core.plugins.exceptions import PermissionDeniedError, PluginExecutionTimeoutError
from shared_core.plugins.middleware import (
    PluginOperationContext,
    apply_middleware,
    audit_middleware,
    build_permission_middleware,
    build_sandbox_middleware,
    logging_middleware,
    metrics_collection_middleware,
)
from shared_core.plugins.permissions import PermissionRegistry, PluginPermission
from shared_core.plugins.sandbox import PluginSandbox, SandboxPolicy

# --- middleware.py ---


def _context(**overrides: object) -> PluginOperationContext:
    defaults: dict[str, object] = {"plugin_id": "sample", "operation": "start"}
    defaults.update(overrides)
    return PluginOperationContext(**defaults)  # type: ignore[arg-type]


async def test_apply_middleware_runs_in_outermost_first_order() -> None:
    calls: list[str] = []

    async def handler(_context: PluginOperationContext) -> str:
        calls.append("handler")
        return "done"

    async def outer(
        context: PluginOperationContext,
        next_handler: Callable[[PluginOperationContext], Awaitable[str]],
    ) -> str:
        calls.append("outer-before")
        result = await next_handler(context)
        calls.append("outer-after")
        return result

    async def inner(
        context: PluginOperationContext,
        next_handler: Callable[[PluginOperationContext], Awaitable[str]],
    ) -> str:
        calls.append("inner-before")
        result = await next_handler(context)
        calls.append("inner-after")
        return result

    wrapped = apply_middleware(handler, [outer, inner])
    result = await wrapped(_context())

    assert result == "done"
    assert calls == ["outer-before", "inner-before", "handler", "inner-after", "outer-after"]


async def test_logging_middleware_passes_through_on_success() -> None:
    async def handler(_context: PluginOperationContext) -> str:
        return "ok"

    wrapped = apply_middleware(handler, [logging_middleware])

    assert await wrapped(_context()) == "ok"


async def test_logging_middleware_reraises_on_failure() -> None:
    async def handler(_context: PluginOperationContext) -> str:
        raise RuntimeError("boom")

    wrapped = apply_middleware(handler, [logging_middleware])

    with pytest.raises(RuntimeError, match="boom"):
        await wrapped(_context())


async def test_permission_middleware_allows_when_granted() -> None:
    permissions = PermissionRegistry()
    permissions.grant("sample", frozenset({PluginPermission.NETWORK}))

    async def handler(_context: PluginOperationContext) -> str:
        return "ok"

    wrapped = apply_middleware(handler, [build_permission_middleware(permissions)])

    result = await wrapped(_context(required_permission=PluginPermission.NETWORK))

    assert result == "ok"


async def test_permission_middleware_denies_when_ungranted() -> None:
    permissions = PermissionRegistry()

    async def handler(_context: PluginOperationContext) -> str:
        return "unreachable"

    wrapped = apply_middleware(handler, [build_permission_middleware(permissions)])

    with pytest.raises(PermissionDeniedError):
        await wrapped(_context(required_permission=PluginPermission.NETWORK))


async def test_permission_middleware_is_a_no_op_when_no_permission_required() -> None:
    permissions = PermissionRegistry()

    async def handler(_context: PluginOperationContext) -> str:
        return "ok"

    wrapped = apply_middleware(handler, [build_permission_middleware(permissions)])

    assert await wrapped(_context()) == "ok"


async def test_sandbox_middleware_enforces_the_configured_sandbox() -> None:
    sandboxes = {"sample": PluginSandbox("sample", SandboxPolicy(execution_timeout_seconds=0.01))}

    async def handler(_context: PluginOperationContext) -> None:
        await asyncio.sleep(10)

    wrapped = apply_middleware(handler, [build_sandbox_middleware(sandboxes)])

    with pytest.raises(PluginExecutionTimeoutError):
        await wrapped(_context())


async def test_sandbox_middleware_passes_through_without_a_configured_sandbox() -> None:
    async def handler(_context: PluginOperationContext) -> str:
        return "ok"

    wrapped = apply_middleware(handler, [build_sandbox_middleware({})])

    assert await wrapped(_context()) == "ok"


async def test_audit_middleware_reraises_and_audits_on_failure() -> None:
    async def handler(_context: PluginOperationContext) -> None:
        raise RuntimeError("boom")

    wrapped = apply_middleware(handler, [audit_middleware])

    with pytest.raises(RuntimeError, match="boom"):
        await wrapped(_context())


async def test_metrics_collection_middleware_passes_through() -> None:
    async def handler(_context: PluginOperationContext) -> str:
        return "ok"

    wrapped = apply_middleware(handler, [metrics_collection_middleware])

    assert await wrapped(_context()) == "ok"


# --- decorators.py ---


def test_hook_marks_the_function() -> None:
    @hook("before_startup")
    async def callback() -> None:
        return None

    assert get_hook_name(callback) == "before_startup"


def test_get_hook_name_returns_none_when_unmarked() -> None:
    async def callback() -> None:
        return None

    assert get_hook_name(callback) is None


def test_extension_marks_the_function() -> None:
    @extension("ui", "menus")
    def contribute() -> dict[str, str]:
        return {"label": "Home"}

    assert get_extension_target(contribute) == ("ui", "menus")


def test_get_extension_target_returns_none_when_unmarked() -> None:
    def contribute() -> None:
        return None

    assert get_extension_target(contribute) is None


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


async def test_timed_returns_the_wrapped_result() -> None:
    @timed("sample")
    async def handler() -> str:
        return "value"

    assert await handler() == "value"


async def test_timed_reraises_on_failure() -> None:
    @timed("sample")
    async def handler() -> None:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        await handler()
