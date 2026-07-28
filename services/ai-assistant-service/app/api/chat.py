"""``/ai/chat`` and ``/ai/conversations``.

``POST /ai/chat/stream`` is implemented as a real
``StreamingResponse`` emitting Server-Sent Events. **Honest note**: the
underlying provider call is not yet streamed token-by-token -- the
answer is produced, then delivered as SSE frames. That gives a client
the correct wire protocol and incremental delivery semantics to build
against, without pretending token-level streaming exists when the
provider clients here use non-streaming endpoints. Closing that gap
means adding streaming request support to each provider client, which
is a per-provider change rather than a change to this route.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from shared_core.logging.context import get_log_context

from app.api.deps import ChatSvc, ConversationSvc, CurrentUserId
from app.models.ai_conversation import AiConversation
from app.models.ai_message import AiMessage
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    ConversationResponse,
    MessageResponse,
    MultiAgentRequest,
    MultiAgentResponse,
)
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/ai", tags=["AI Chat"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def conversation_to_response(conversation: AiConversation) -> ConversationResponse:
    """Map a conversation row onto its own response schema."""
    return ConversationResponse(
        id=conversation.id,
        organization_id=conversation.organization_id,
        project_id=conversation.project_id,
        session_id=conversation.session_id,
        user_id=conversation.user_id,
        title=conversation.title,
        status=conversation.status,
        started_at=conversation.started_at,
        completed_at=conversation.completed_at,
    )


def message_to_response(message: AiMessage) -> MessageResponse:
    """Map a message row onto its own response schema."""
    return MessageResponse(
        id=message.id,
        conversation_id=message.conversation_id,
        sequence=message.sequence,
        role=message.role,
        content=message.content,
        model=message.model,
        provider=message.provider,
        prompt_tokens=message.prompt_tokens,
        completion_tokens=message.completion_tokens,
        latency_ms=message.latency_ms,
        citations=message.citations,
    )


async def _resolve_conversation(
    body: ChatRequest, chat: ChatSvc, conversations: ConversationSvc, caller: UUID
) -> AiConversation:
    """Continue the named conversation, or open a new one.

    A new conversation is titled from the first message, truncated --
    a thread listing is far more usable than one showing "New chat"
    for every row.

    Raises:
        NotFoundError: If a named conversation does not exist.
    """
    if body.conversation_id is not None:
        return await conversations.get_by_id(body.conversation_id)
    return await chat.start_conversation(
        organization_id=body.organization_id,
        project_id=body.project_id,
        user_id=caller,
        title=body.message[:120],
        session_id=body.session_id,
    )


@router.post("/chat", response_model=SuccessResponse[ChatResponse], status_code=201)
async def send_chat(
    body: ChatRequest,
    chat: ChatSvc,
    conversations: ConversationSvc,
    caller: CurrentUserId,
) -> SuccessResponse[ChatResponse]:
    """Send one message and get the assistant's own answer.

    Raises:
        NotFoundError: If a named conversation does not exist.
        AIError: If no agent is configured or every provider failed.
    """
    conversation = await _resolve_conversation(body, chat, conversations, caller)
    turn = await chat.send(
        conversation,
        body.message,
        caller_permissions=body.caller_permissions,
        allow_mutating_tools=body.allow_mutating_tools,
        agent_type=body.agent_type,
        requested_by=caller,
    )
    return SuccessResponse(
        message="Assistant replied.",
        data=ChatResponse(
            conversation_id=conversation.id,
            message_id=turn.assistant_message.id,
            content=turn.assistant_message.content,
            citations=turn.citations,
            tool_calls_made=turn.tool_calls_made,
            guardrail_findings=turn.guardrail_findings,
            provider=turn.provider,
            model=turn.model,
        ),
        meta=_meta(),
    )


@router.post("/chat/stream")
async def send_chat_stream(
    body: ChatRequest,
    chat: ChatSvc,
    conversations: ConversationSvc,
    caller: CurrentUserId,
) -> StreamingResponse:
    """Send one message and receive the answer as Server-Sent Events.

    Emits ``meta`` (ids and model), then ``delta`` frames carrying the
    answer, then ``done``. See this module's own docstring for the
    honest limit on token-level streaming.
    """
    conversation = await _resolve_conversation(body, chat, conversations, caller)
    turn = await chat.send(
        conversation,
        body.message,
        caller_permissions=body.caller_permissions,
        allow_mutating_tools=body.allow_mutating_tools,
        agent_type=body.agent_type,
        requested_by=caller,
    )

    async def _events() -> AsyncIterator[str]:
        yield _sse(
            "meta",
            {
                "conversation_id": str(conversation.id),
                "message_id": str(turn.assistant_message.id),
                "provider": turn.provider,
                "model": turn.model,
            },
        )
        content = turn.assistant_message.content
        # Chunked so a client's own incremental rendering path is
        # genuinely exercised rather than receiving one giant frame.
        for start in range(0, len(content), 256):
            yield _sse("delta", {"text": content[start : start + 256]})
        yield _sse("done", {"citations": turn.citations})

    return StreamingResponse(
        _events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _sse(event: str, payload: dict[str, object]) -> str:
    """Format one Server-Sent Event frame."""
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"


@router.post(
    "/chat/multi-agent", response_model=SuccessResponse[MultiAgentResponse], status_code=201
)
async def send_multi_agent(
    body: MultiAgentRequest,
    chat: ChatSvc,
    conversations: ConversationSvc,
    caller: CurrentUserId,
) -> SuccessResponse[MultiAgentResponse]:
    """Decompose a request across agents and return the aggregated answer.

    Added beyond docs/046's own literal REST list: "Multi-Agent
    Framework" is an explicit ACCEPTANCE CRITERIA line with no endpoint
    of its own, so orchestration would otherwise be unreachable.

    Raises:
        NotFoundError: If a named conversation does not exist.
    """
    conversation = (
        await conversations.get_by_id(body.conversation_id)
        if body.conversation_id is not None
        else await chat.start_conversation(
            organization_id=body.organization_id,
            project_id=body.project_id,
            user_id=caller,
            title=body.request[:120],
        )
    )
    content = await chat.run_multi_agent(conversation, body.request, parallel=body.parallel)
    return SuccessResponse(
        message="Multi-agent run completed.",
        data=MultiAgentResponse(conversation_id=conversation.id, content=content),
        meta=_meta(),
    )


@router.get("/conversations", response_model=SuccessResponse[list[ConversationResponse]])
async def list_conversations(
    organization_id: UUID,
    conversations: ConversationSvc,
    caller: CurrentUserId,
    mine_only: bool = False,
) -> SuccessResponse[list[ConversationResponse]]:
    """List conversations, optionally only the caller's own."""
    records = (
        await conversations.list_for_user(organization_id, caller)
        if mine_only
        else await conversations.list_for_org(organization_id)
    )
    return SuccessResponse(
        message="Conversations retrieved.",
        data=[conversation_to_response(record) for record in records],
        meta=_meta(),
    )


@router.get(
    "/conversations/{conversation_id}", response_model=SuccessResponse[ConversationResponse]
)
async def get_conversation(
    conversation_id: UUID, conversations: ConversationSvc, _caller: CurrentUserId
) -> SuccessResponse[ConversationResponse]:
    """Return one conversation.

    Raises:
        NotFoundError: If no such conversation exists.
    """
    conversation = await conversations.get_by_id(conversation_id)
    return SuccessResponse(
        message="Conversation retrieved.",
        data=conversation_to_response(conversation),
        meta=_meta(),
    )


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=SuccessResponse[list[MessageResponse]],
)
async def list_conversation_messages(
    conversation_id: UUID, conversations: ConversationSvc, _caller: CurrentUserId
) -> SuccessResponse[list[MessageResponse]]:
    """Every turn in a conversation, in order."""
    records = await conversations.list_messages(conversation_id)
    return SuccessResponse(
        message="Messages retrieved.",
        data=[message_to_response(record) for record in records],
        meta=_meta(),
    )


__all__ = ["conversation_to_response", "message_to_response", "router"]
