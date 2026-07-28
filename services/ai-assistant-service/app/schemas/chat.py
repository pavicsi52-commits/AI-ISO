"""Request/response schemas for ``/ai/chat`` and ``/ai/conversations``."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import AgentType, ConversationStatus, MessageRole, ToolCallStatus


class ChatRequest(BaseModel):
    """Body of ``POST /ai/chat``.

    ``conversation_id`` is optional: omitting it starts a new thread,
    which is what a first message always does.

    ``allow_mutating_tools`` defaults to **false** deliberately. A
    mutating tool can change real infrastructure, so it must be an
    explicit per-request opt-in rather than something a model can reach
    by default.
    """

    organization_id: UUID
    project_id: UUID | None = None
    conversation_id: UUID | None = None
    session_id: UUID | None = None
    message: str = Field(min_length=1)
    agent_type: AgentType | None = None
    allow_mutating_tools: bool = False
    caller_permissions: list[str] = Field(default_factory=list)


class CitationResponse(BaseModel):
    """One source the answer drew on."""

    chunk_id: str
    document_id: str
    title: str
    uri: str | None = None
    score: float


class ChatResponse(BaseModel):
    """What one chat turn produced."""

    conversation_id: UUID
    message_id: UUID
    content: str
    citations: list[dict[str, Any]] = Field(default_factory=list)
    tool_calls_made: int = 0
    guardrail_findings: list[str] = Field(default_factory=list)
    provider: str | None = None
    model: str | None = None


class ConversationResponse(BaseModel):
    """One conversation thread."""

    id: UUID
    organization_id: UUID
    project_id: UUID | None
    session_id: UUID | None
    user_id: UUID
    title: str
    status: ConversationStatus
    started_at: datetime
    completed_at: datetime | None


class MessageResponse(BaseModel):
    """One turn in a conversation."""

    id: UUID
    conversation_id: UUID
    sequence: int
    role: MessageRole
    content: str
    model: str | None
    provider: str | None
    prompt_tokens: int
    completion_tokens: int
    latency_ms: float | None
    citations: list[dict[str, Any]]


class MultiAgentRequest(BaseModel):
    """Body of ``POST /ai/chat/multi-agent``."""

    organization_id: UUID
    project_id: UUID | None = None
    conversation_id: UUID | None = None
    request: str = Field(min_length=1)
    parallel: bool = Field(
        default=False,
        description=(
            "Run independent tasks concurrently. Faster, but tasks cannot "
            "see each other's findings."
        ),
    )


class MultiAgentResponse(BaseModel):
    """The aggregated answer from a multi-agent run."""

    conversation_id: UUID
    content: str


__all__ = [
    "ChatRequest",
    "ChatResponse",
    "CitationResponse",
    "ConversationResponse",
    "MessageResponse",
    "MultiAgentRequest",
    "MultiAgentResponse",
]


class SessionCreateRequest(BaseModel):
    """Body of ``POST /ai/sessions``."""

    organization_id: UUID
    project_id: UUID | None = None
    label: str | None = Field(default=None, max_length=255)
    expires_at: datetime | None = None


class SessionResponse(BaseModel):
    """One working session."""

    id: UUID
    organization_id: UUID
    project_id: UUID | None
    user_id: UUID
    label: str | None
    started_at: datetime
    last_active_at: datetime
    expires_at: datetime | None
    is_open: bool


class ToolCallResponse(BaseModel):
    """One recorded tool call together with its result.

    ``result`` is ``null`` for a denied call: nothing ran, and that
    absence distinguishes "blocked" from "never attempted".
    """

    id: UUID
    conversation_id: UUID | None
    tool_id: UUID
    arguments: dict[str, Any]
    status: ToolCallStatus
    denial_reason: str | None
    requested_by: UUID | None
    started_at: datetime | None
    finished_at: datetime | None
    succeeded: bool | None = None
    result: dict[str, Any] | None = None
    error_message: str | None = None
    duration_ms: float | None = None
