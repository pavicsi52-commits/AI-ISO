"""Tool execution with full trace persistence (docs/060 "TOOL
EXECUTION").

Runs one requested tool call end to end: authorize, validate, execute,
record. Mirrors ``ai-assistant-service``'s own ``app/tool_calling
/executor.py`` (Prompt 046) ``ToolExecutor`` shape, adapted to this
service's own compact schema: there is no dedicated tool-call/tool-
result table here (docs/060's own 17-table design keeps every tool
invocation as one entry inside :attr:`~app.models.execution
.AgentExecution.trace`, plus its own running ``tool_calls_made``
counter), so "record" means appending to the *in-memory*
:class:`~app.models.execution.AgentExecution` this executor was handed,
not writing new rows. Persisting the mutated execution stays the
caller's own job -- whatever service holds
:class:`~app.repositories.execution.AgentExecutionRepository` -- which
keeps this executor free of any direct database dependency and
testable without one.

Every path -- denied, invalid, failed, succeeded -- becomes one trace
entry. That is what makes the audit trail complete rather than
"complete except when something went wrong".

Tool *results* are redacted before being recorded or handed back to the
model: a tool that reads a config file or a knowledge-graph fact can
easily return a credential, and neither the trace nor the model may
ever see it.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from shared_core.logging.logger import get_logger

from app.events.agent_events import ToolInvokedEvent
from app.guardrails.redaction import redact
from app.models.enums import PermissionCategory, ToolCallStatus
from app.models.execution import AgentExecution
from app.models.tool import AgentTool
from app.tool_registry.registry import ToolHandlerRegistry, authorize, validate_arguments
from app.types import EventPublisher

logger = get_logger("app.tool_execution.executor")


@dataclass(frozen=True, slots=True)
class ToolCallOutcome:
    """The outcome of one tool call."""

    tool_key: str
    status: ToolCallStatus
    result: dict[str, Any] | None = None
    error: str | None = None
    denial_reason: str | None = None
    duration_ms: float = 0.0

    @property
    def succeeded(self) -> bool:
        """Whether the tool ran and returned successfully."""
        return self.status is ToolCallStatus.SUCCEEDED

    def as_model_content(self) -> str:
        """What to feed back to the model as a ``tool``-role turn.

        A denial or failure is reported to the model in plain language
        rather than hidden: an agent should be able to tell its caller
        "I could not do that because I lack permission", which is far
        more useful than an unexplained gap.
        """
        if self.status is ToolCallStatus.DENIED:
            return f"Tool call was not executed: {self.denial_reason or 'unknown reason'}."
        if not self.succeeded:
            return f"Tool call failed: {self.error or 'unknown error'}."
        return str(self.result)


class ToolExecutor:
    """Authorizes, runs, and records tool calls onto an in-memory
    :class:`AgentExecution`."""

    def __init__(self, handlers: ToolHandlerRegistry, *, publish_event: EventPublisher) -> None:
        self._handlers = handlers
        self._publish_event = publish_event

    async def execute(
        self,
        tool: AgentTool,
        arguments: dict[str, Any],
        *,
        execution: AgentExecution,
        agent_tool_keys: list[str],
        granted_categories: list[PermissionCategory],
        allow_mutating: bool = False,
    ) -> ToolCallOutcome:
        """Run one tool call, recording it onto *execution* and
        announcing every outcome.

        The ``ToolInvoked`` event is emitted for *every* terminal
        outcome, including a denial. A refused invocation is precisely
        what a downstream audit consumer needs to see -- publishing only
        successes would make the permission gate invisible.
        """
        outcome = await self._run(
            tool,
            arguments,
            agent_tool_keys=agent_tool_keys,
            granted_categories=granted_categories,
            allow_mutating=allow_mutating,
        )
        self._record(execution, tool, arguments, outcome)
        await self._publish_event(
            ToolInvokedEvent(
                source_service="ai-agent-platform-service",
                payload={
                    "execution_id": str(execution.id),
                    "agent_id": str(execution.agent_id),
                    "tool_key": tool.tool_key,
                    "status": str(outcome.status),
                },
            )
        )
        return outcome

    async def _run(
        self,
        tool: AgentTool,
        arguments: dict[str, Any],
        *,
        agent_tool_keys: list[str],
        granted_categories: list[PermissionCategory],
        allow_mutating: bool,
    ) -> ToolCallOutcome:
        """Authorize, validate, and run one tool call."""
        decision = authorize(
            tool,
            agent_tool_keys=agent_tool_keys,
            granted_categories=granted_categories,
            allow_mutating=allow_mutating,
        )
        if not decision.allowed:
            return ToolCallOutcome(
                tool_key=tool.tool_key,
                status=ToolCallStatus.DENIED,
                denial_reason=decision.reason or "Not authorized.",
            )

        validation_error = validate_arguments(tool, arguments)
        if validation_error is not None:
            return ToolCallOutcome(
                tool_key=tool.tool_key,
                status=ToolCallStatus.DENIED,
                denial_reason=validation_error,
            )

        handler = self._handlers.get(tool.tool_key)
        if handler is None:
            return ToolCallOutcome(
                tool_key=tool.tool_key,
                status=ToolCallStatus.DENIED,
                denial_reason=f"Tool {tool.tool_key!r} has no registered handler.",
            )

        started = time.monotonic()
        try:
            raw = await handler(arguments)
        except Exception as exc:
            logger.warning(
                "Tool handler raised.",
                extra={"extra_fields": {"tool_key": tool.tool_key, "error": str(exc)}},
            )
            return ToolCallOutcome(
                tool_key=tool.tool_key,
                status=ToolCallStatus.FAILED,
                error=str(exc),
                duration_ms=(time.monotonic() - started) * 1000,
            )

        # Redact before the result can reach the model's own context or the trace.
        redaction = redact(str(raw))
        payload = raw if not redaction.was_redacted else {"redacted": redaction.text}

        return ToolCallOutcome(
            tool_key=tool.tool_key,
            status=ToolCallStatus.SUCCEEDED,
            result=payload,
            duration_ms=(time.monotonic() - started) * 1000,
        )

    def _record(
        self,
        execution: AgentExecution,
        tool: AgentTool,
        arguments: dict[str, Any],
        outcome: ToolCallOutcome,
    ) -> None:
        """Append this call to *execution*'s own trace.

        Reassigns ``trace``/``tool_calls_made`` rather than mutating
        the existing list in place -- this platform's own established
        convention for JSON-list columns, since SQLAlchemy's change
        tracking does not see an in-place ``list.append``.
        """
        entry = {
            "type": "tool_call",
            "tool_key": tool.tool_key,
            "arguments": arguments,
            "status": str(outcome.status),
            "result": outcome.result,
            "error": outcome.error,
            "denial_reason": outcome.denial_reason,
            "duration_ms": outcome.duration_ms,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        execution.trace = [*execution.trace, entry]
        execution.tool_calls_made += 1


__all__ = ["ToolCallOutcome", "ToolExecutor"]
