"""Tool execution with full persistence.

Runs one requested tool call end to end: authorize, validate, execute,
record. Every path -- denied, invalid, failed, succeeded -- writes an
:class:`~app.models.ai_tool_call.AiToolCall` row, and every path that
actually ran writes an :class:`~app.models.ai_tool_result.AiToolResult`
beside it. That is what makes the audit trail complete rather than
"complete except when something went wrong".

Tool *results* are redacted before being handed back to the model: a
tool that reads a config file or an inventory record can easily return
a credential, and the model must never see it.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.logging.logger import get_logger

from app.events.ai_events import ToolCalledEvent
from app.guardrails.redaction import redact
from app.models.ai_tool import AiTool
from app.models.ai_tool_call import AiToolCall
from app.models.ai_tool_result import AiToolResult
from app.models.enums import ToolCallStatus
from app.repositories.ai_tool_call import AiToolCallRepository
from app.repositories.ai_tool_result import AiToolResultRepository
from app.tool_calling.registry import (
    ToolHandlerRegistry,
    authorize,
    validate_arguments,
)
from app.types import EventPublisher

logger = get_logger("app.tool_calling.executor")


@dataclass(frozen=True, slots=True)
class ToolExecution:
    """The outcome of one tool call, as persisted."""

    call: AiToolCall
    result: AiToolResult | None
    status: ToolCallStatus

    @property
    def succeeded(self) -> bool:
        """Whether the tool ran and returned successfully."""
        return self.status is ToolCallStatus.SUCCEEDED

    def as_model_content(self) -> str:
        """What to feed back to the model as a ``TOOL``-role turn.

        A denial or failure is reported to the model in plain language
        rather than hidden: the assistant should be able to tell the
        user "I could not check that because you lack permission",
        which is far more useful than an unexplained gap.
        """
        if self.result is None:
            return f"Tool call was not executed: {self.call.denial_reason or 'unknown reason'}."
        if not self.result.succeeded:
            return f"Tool call failed: {self.result.error_message or 'unknown error'}."
        return str(self.result.result)


class ToolExecutor:
    """Authorizes, runs, and records tool calls."""

    def __init__(
        self,
        calls: AiToolCallRepository,
        results: AiToolResultRepository,
        handlers: ToolHandlerRegistry,
        *,
        publish_event: EventPublisher,
    ) -> None:
        self._calls = calls
        self._results = results
        self._handlers = handlers
        self._publish_event = publish_event

    async def execute(
        self,
        tool: AiTool,
        arguments: dict[str, Any],
        *,
        organization_id: UUID,
        project_id: UUID | None = None,
        conversation_id: UUID | None = None,
        message_id: UUID | None = None,
        requested_by: UUID | None = None,
        agent_tool_keys: list[str],
        caller_permissions: list[str],
        allow_mutating: bool = False,
    ) -> ToolExecution:
        """Run one tool call, recording and announcing every outcome.

        The ``ToolCalled`` event is emitted for *every* terminal
        outcome, including a denial. A refused invocation is precisely
        what a downstream audit consumer needs to see -- publishing only
        successes would make the permission gate invisible.
        """
        execution = await self._execute(
            tool,
            arguments,
            organization_id=organization_id,
            project_id=project_id,
            conversation_id=conversation_id,
            message_id=message_id,
            requested_by=requested_by,
            agent_tool_keys=agent_tool_keys,
            caller_permissions=caller_permissions,
            allow_mutating=allow_mutating,
        )
        await self._publish_event(
            ToolCalledEvent(
                source_service="ai-assistant-service",
                payload={
                    "tool_call_id": str(execution.call.id),
                    "tool_key": tool.tool_key,
                    "status": str(execution.status),
                    "conversation_id": str(conversation_id) if conversation_id else None,
                },
            )
        )
        return execution

    async def _execute(
        self,
        tool: AiTool,
        arguments: dict[str, Any],
        *,
        organization_id: UUID,
        project_id: UUID | None = None,
        conversation_id: UUID | None = None,
        message_id: UUID | None = None,
        requested_by: UUID | None = None,
        agent_tool_keys: list[str],
        caller_permissions: list[str],
        allow_mutating: bool = False,
    ) -> ToolExecution:
        """Authorize, run, and record one tool call."""
        call = await self._calls.create(
            AiToolCall(
                organization_id=organization_id,
                project_id=project_id,
                conversation_id=conversation_id,
                message_id=message_id,
                tool_id=tool.id,
                arguments=arguments,
                status=ToolCallStatus.PENDING,
                requested_by=requested_by,
            )
        )

        decision = authorize(
            tool,
            agent_tool_keys=agent_tool_keys,
            caller_permissions=caller_permissions,
            allow_mutating=allow_mutating,
        )
        if not decision.allowed:
            return await self._deny(call, decision.reason or "Not authorized.")

        validation_error = validate_arguments(tool, arguments)
        if validation_error is not None:
            return await self._deny(call, validation_error)

        handler = self._handlers.get(tool.tool_key)
        if handler is None:
            return await self._deny(call, f"Tool {tool.tool_key!r} has no registered handler.")

        call.status = ToolCallStatus.RUNNING
        call.started_at = datetime.now(UTC)
        call = await self._calls.update(call)

        started = time.monotonic()
        try:
            raw = await handler(arguments)
        except Exception as exc:
            logger.warning(
                "Tool handler raised.",
                extra={"extra_fields": {"tool_key": tool.tool_key, "error": str(exc)}},
            )
            return await self._finish(
                call,
                succeeded=False,
                payload={},
                error_message=str(exc),
                duration_ms=(time.monotonic() - started) * 1000,
            )

        # Redact before the result can reach the model's own context.
        redaction = redact(str(raw))
        payload = raw if not redaction.was_redacted else {"redacted": redaction.text}

        return await self._finish(
            call,
            succeeded=True,
            payload=payload,
            error_message=None,
            duration_ms=(time.monotonic() - started) * 1000,
        )

    async def _deny(self, call: AiToolCall, reason: str) -> ToolExecution:
        call.status = ToolCallStatus.DENIED
        call.denial_reason = reason
        call.finished_at = datetime.now(UTC)
        stored = await self._calls.update(call)
        return ToolExecution(call=stored, result=None, status=ToolCallStatus.DENIED)

    async def _finish(
        self,
        call: AiToolCall,
        *,
        succeeded: bool,
        payload: dict[str, Any],
        error_message: str | None,
        duration_ms: float,
    ) -> ToolExecution:
        status = ToolCallStatus.SUCCEEDED if succeeded else ToolCallStatus.FAILED
        call.status = status
        call.finished_at = datetime.now(UTC)
        stored = await self._calls.update(call)

        result = await self._results.create(
            AiToolResult(
                organization_id=call.organization_id,
                project_id=call.project_id,
                tool_call_id=stored.id,
                succeeded=succeeded,
                result=payload,
                error_message=error_message,
                duration_ms=duration_ms,
            )
        )
        return ToolExecution(call=stored, result=result, status=status)


__all__ = ["ToolExecution", "ToolExecutor"]
