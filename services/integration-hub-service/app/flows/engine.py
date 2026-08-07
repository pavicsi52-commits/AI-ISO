"""Integration flow execution (docs/058 "INTEGRATION FLOWS").

A genuine gap -- no generic step-graph execution engine exists in
`shared_core`. Built new, pure at its core: this module never touches
the database or network directly. What one ``"action"`` step actually
*does* is supplied by the caller as a `StepExecutor` callback (a
`FlowService` in the service layer binds this to real sync/transform/
event-publish behavior) -- this engine only owns traversal order,
condition evaluation, retries, error handling, compensation, approval
gating, and parallel fan-out.

**Definition shape** (stored as ``ConnectorFlow.definition`` JSON)::

    {
        "start": "s1",
        "steps": {
            "s1": {"kind": "action", "action": "sync", "config": {...}, "next": "s2"},
            "s2": {"kind": "condition", "rule": {...}, "then": "s3", "else": "s4"},
            "s3": {"kind": "loop", "over": "items", "body": "s5", "max_iterations": 100},
            "s4": {"kind": "parallel", "branches": ["s6", "s7"], "next": "s8"},
            "s5": {"kind": "action", "action": "process_item", "next": None},
            "s6": {"kind": "approval", "next": "s8"},
            "s8": {"kind": "action", "action": "notify", "on_error": "s9"},
            "s9": {"kind": "compensation", "action": "rollback"},
        },
    }

Every step but ``condition``/``branch`` carries a ``"next"`` (the step
id to run afterward, or ``None`` to stop); ``condition`` carries
``"then"``/``"else"`` instead. A step may set ``"max_attempts"`` (retried
with `shared_core.queue.retry.compute_backoff_delay`-style exponential
backoff between attempts) and ``"on_error"`` (another step id to jump to
-- typically a ``compensation`` step -- instead of failing the whole run).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from shared_core.queue.retry import compute_backoff_delay

from app.models.enums import FlowStepKind

StepExecutor = Callable[[str, Mapping[str, Any], dict[str, Any]], Awaitable[dict[str, Any]]]
"""``(action_name, step_config, context) -> result``. Raises on failure."""

_MAX_STEPS_PER_RUN = 10_000
"""A hard ceiling on total step executions in one run, guarding a
malformed definition (e.g. a loop or branch cycle) from running forever."""


class FlowExecutionError(Exception):
    """A flow run failed and had no ``on_error`` step to recover through."""


@dataclass(slots=True)
class FlowRunResult:
    """The outcome of one flow run."""

    status: str
    """``"succeeded"``, ``"failed"``, or ``"awaiting_approval"``."""
    context: dict[str, Any]
    steps_executed: list[str] = field(default_factory=list)
    error: str | None = None
    awaiting_step: str | None = None


_CONDITION_COMPARATORS: dict[str, Callable[[Any, Any], bool]] = {
    "eq": lambda actual, expected: bool(actual == expected),
    "ne": lambda actual, expected: bool(actual != expected),
    "gt": lambda actual, expected: bool(actual > expected),
    "lt": lambda actual, expected: bool(actual < expected),
    "in": lambda actual, expected: expected is not None and actual in expected,
}


def _evaluate_condition(rule: Mapping[str, Any], context: Mapping[str, Any]) -> bool:
    """A ``{"field", "operator", "value"}`` rule evaluated against *context* --
    the same minimal rule shape this platform's filter/routing engines share."""
    operator = rule.get("operator", "eq")
    field_path = str(rule.get("field", ""))
    actual: Any = context
    for part in field_path.split("."):
        actual = actual.get(part) if isinstance(actual, Mapping) else None
    if operator == "exists":
        return actual is not None
    if actual is None:
        return False
    comparator = _CONDITION_COMPARATORS.get(operator)
    return comparator(actual, rule.get("value")) if comparator is not None else False


class FlowEngine:
    """Executes one flow definition against a caller-supplied step executor."""

    def __init__(
        self, *, executor: StepExecutor, sleep: Callable[[float], Awaitable[None]] | None = None
    ) -> None:
        self._executor = executor
        self._sleep = sleep or asyncio.sleep

    async def run(
        self, definition: Mapping[str, Any], *, context: dict[str, Any] | None = None
    ) -> FlowRunResult:
        """Execute *definition* from its own ``"start"`` step."""
        steps: Mapping[str, Any] = definition.get("steps", {})
        result = FlowRunResult(status="succeeded", context=dict(context or {}))
        current: str | None = definition.get("start")
        executed = 0

        while current is not None:
            executed += 1
            if executed > _MAX_STEPS_PER_RUN:
                result.status = "failed"
                result.error = (
                    f"Exceeded {_MAX_STEPS_PER_RUN} step executions -- likely a definition cycle."
                )
                return result
            step = steps.get(current)
            if step is None:
                result.status = "failed"
                result.error = f"Flow definition references unknown step {current!r}."
                return result
            result.steps_executed.append(current)

            try:
                current = await self._run_step(current, step, steps, result.context)
            except FlowExecutionError as exc:
                on_error = step.get("on_error")
                if on_error is None:
                    result.status = "failed"
                    result.error = str(exc)
                    return result
                result.context["last_error"] = str(exc)
                current = on_error
                continue

            if current == "__AWAITING_APPROVAL__":
                result.status = "awaiting_approval"
                result.awaiting_step = result.steps_executed[-1]
                return result

        return result

    async def _run_step(
        self,
        step_id: str,
        step: Mapping[str, Any],
        steps: Mapping[str, Any],
        context: dict[str, Any],
    ) -> str | None:
        kind = FlowStepKind(step.get("kind", FlowStepKind.ACTION))

        if kind == FlowStepKind.CONDITION:
            matched = _evaluate_condition(step.get("rule", {}), context)
            return step.get("then") if matched else step.get("else")

        if kind == FlowStepKind.APPROVAL and not context.get(f"_approved_{step_id}"):
            return "__AWAITING_APPROVAL__"

        if kind == FlowStepKind.LOOP:
            await self._run_loop(step, steps, context)
        elif kind == FlowStepKind.PARALLEL:
            await self._run_parallel(step, steps, context)
        elif kind == FlowStepKind.COMPENSATION:
            await self._execute_action(step, context)
        elif kind != FlowStepKind.APPROVAL:
            return await self._run_action_with_retry(step, context)

        return step.get("next")

    async def _run_loop(
        self, step: Mapping[str, Any], steps: Mapping[str, Any], context: dict[str, Any]
    ) -> None:
        over = context.get(step.get("over", ""), [])
        body_step_id = step.get("body")
        max_iterations = int(step.get("max_iterations", 1_000))
        for index, item in enumerate(over[:max_iterations]):
            context["_loop_item"] = item
            context["_loop_index"] = index
            await self._run_body(body_step_id, steps, context)

    async def _run_parallel(
        self, step: Mapping[str, Any], steps: Mapping[str, Any], context: dict[str, Any]
    ) -> None:
        branches = step.get("branches", [])
        await asyncio.gather(*(self._run_body(branch, steps, context) for branch in branches))

    async def _run_action_with_retry(
        self, step: Mapping[str, Any], context: dict[str, Any]
    ) -> str | None:
        """Run an ``ACTION`` step, retried per its own ``max_attempts`` with exponential backoff."""
        max_attempts = int(step.get("max_attempts", 1))
        last_error: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                await self._execute_action(step, context)
                return step.get("next")
            except Exception as exc:  # any executor failure is a retryable step failure here
                last_error = exc
                if attempt < max_attempts:
                    await self._sleep(
                        compute_backoff_delay(attempt, base_seconds=1.0, max_seconds=30.0)
                    )
        raise FlowExecutionError(str(last_error))

    async def _run_body(
        self, step_id: str | None, steps: Mapping[str, Any], context: dict[str, Any]
    ) -> None:
        """Run one step (and its own ``"next"`` chain) as a nested sub-sequence,
        used by ``LOOP``/``PARALLEL`` bodies -- never crosses back into approval-gating."""
        current = step_id
        while current is not None:
            step = steps.get(current)
            if step is None:
                raise FlowExecutionError(f"Flow definition references unknown step {current!r}.")
            current = await self._run_step(current, step, steps, context)
            if current == "__AWAITING_APPROVAL__":
                raise FlowExecutionError(
                    "Approval steps are not supported inside a loop/parallel body."
                )

    async def _execute_action(self, step: Mapping[str, Any], context: dict[str, Any]) -> None:
        action = step.get("action", "")
        outcome = await self._executor(action, step.get("config", {}), context)
        context.update(outcome)


__all__ = ["FlowEngine", "FlowExecutionError", "FlowRunResult", "StepExecutor"]
