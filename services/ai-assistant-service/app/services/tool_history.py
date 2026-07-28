"""Tool-call history -- what the assistant actually *did*.

Every AI-IOS surface that lets a model act has to be able to answer
"what did it do, with what arguments, and what came back?". The
executor already records each call and its result; this is the read
side that makes those records reachable, which is what turns them from
storage into accountability.

Denied calls are included deliberately. A refused invocation is the
most interesting row in an audit -- it shows the permission gate doing
its job -- and hiding it would leave a reader unable to tell "never
attempted" from "attempted and blocked".
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.models.ai_tool_call import AiToolCall
from app.models.ai_tool_result import AiToolResult
from app.repositories.ai_tool_call import AiToolCallRepository
from app.repositories.ai_tool_result import AiToolResultRepository


@dataclass(frozen=True, slots=True)
class ToolCallRecord:
    """One recorded call together with its result, if it produced one.

    ``result`` is ``None`` for a denied call -- nothing ran, so there is
    nothing to report, and that absence is itself the useful signal.
    """

    call: AiToolCall
    result: AiToolResult | None


class ToolHistoryService:
    """Reads recorded tool calls and their results."""

    def __init__(
        self, tool_calls: AiToolCallRepository, tool_results: AiToolResultRepository
    ) -> None:
        self._tool_calls = tool_calls
        self._tool_results = tool_results

    async def list_for_conversation(self, conversation_id: UUID) -> list[ToolCallRecord]:
        """Every tool call made during one conversation, with results.

        Results are fetched sequentially rather than gathered: an
        ``AsyncSession`` is not safe for concurrent use even for reads,
        which is the rule every AI-IOS service has followed since
        ``services/validation-service``.
        """
        calls = await self._tool_calls.list_for_conversation(conversation_id)
        records: list[ToolCallRecord] = []
        for call in calls:
            records.append(
                ToolCallRecord(call=call, result=await self._tool_results.get_for_call(call.id))
            )
        return records

    async def list_for_org(self, organization_id: UUID) -> list[AiToolCall]:
        """Every tool call recorded for an organization."""
        return await self._tool_calls.list_for_org(organization_id)


__all__ = ["ToolCallRecord", "ToolHistoryService"]
