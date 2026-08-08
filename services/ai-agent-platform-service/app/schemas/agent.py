"""Request/response shapes for ``/agents`` (docs/060 "REST APIs")."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import (
    AgentLifecycleStatus,
    AgentType,
    ModelProvider,
    ReasoningMode,
    RoutingStrategy,
)


class ProfilePayload(BaseModel):
    """One agent's own model/reasoning configuration, as submitted by a caller."""

    system_prompt: str | None = None
    model_provider: ModelProvider = ModelProvider.OLLAMA
    model_name: str = "llama3"
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2_048, ge=1, le=200_000)
    reasoning_mode: ReasoningMode = ReasoningMode.TOOL_BASED
    routing_strategy: RoutingStrategy = RoutingStrategy.FALLBACK
    fallback_providers: list[ModelProvider] = Field(default_factory=list)
    allowed_tool_keys: list[str] = Field(default_factory=list)
    max_reasoning_steps: int = Field(default=8, ge=1, le=64)
    extra_config: dict[str, Any] = Field(default_factory=dict)


class AgentRegisterRequest(BaseModel):
    """``POST /agents``."""

    slug: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    agent_type: AgentType
    description: str | None = None
    owner_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    profile: ProfilePayload = Field(default_factory=ProfilePayload)


class AgentUpdateRequest(BaseModel):
    """``PUT /agents/{id}``. ``None`` leaves a field unchanged."""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    owner_id: str | None = None
    tags: list[str] | None = None


class AgentExecuteRequest(BaseModel):
    """``POST /agents/{id}/execute``."""

    request: str = Field(min_length=1)
    session_id: UUID | None = None
    task_id: UUID | None = None
    allow_mutating: bool = False


class AgentResponse(BaseModel):
    """One registered agent."""

    id: UUID
    organization_id: UUID
    slug: str
    name: str
    description: str | None
    agent_type: AgentType
    status: AgentLifecycleStatus
    current_version_number: str | None
    tags: list[str]
    owner_id: str | None
    consecutive_failures: int
    last_executed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AgentExecutionResponse(BaseModel):
    """One recorded agent run."""

    id: UUID
    agent_id: UUID
    task_id: UUID | None
    session_id: UUID | None
    status: str
    reasoning_mode: str
    model_provider: str
    model_name: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    tool_calls_made: int
    reasoning_steps: int
    latency_ms: float | None
    cost_usd: float
    input_summary: str | None
    output_summary: str | None
    trace: list[dict[str, Any]]
    started_at: datetime
    completed_at: datetime | None
    error: str | None

    model_config = {"from_attributes": True}


__all__ = [
    "AgentExecuteRequest",
    "AgentExecutionResponse",
    "AgentRegisterRequest",
    "AgentResponse",
    "AgentUpdateRequest",
    "ProfilePayload",
]
