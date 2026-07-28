"""Request/response schemas for agents and tools."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import AgentType, ModelProvider, ToolKind


class AgentCreateRequest(BaseModel):
    """Body of ``POST /ai/agents``.

    ``tool_keys`` is the agent's own allowlist: a model driving this
    agent physically cannot invoke a tool outside it.
    """

    organization_id: UUID
    project_id: UUID | None = None
    name: str = Field(min_length=1, max_length=255)
    agent_type: AgentType
    description: str | None = None
    provider: ModelProvider
    model: str = Field(min_length=1, max_length=128)
    system_prompt: str | None = None
    tool_keys: list[str] = Field(default_factory=list)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2048, ge=1)
    enabled: bool = True


class AgentResponse(BaseModel):
    """One registered agent."""

    id: UUID
    organization_id: UUID
    project_id: UUID | None
    name: str
    agent_type: AgentType
    description: str | None
    provider: ModelProvider
    model: str
    system_prompt: str | None
    tool_keys: list[str]
    temperature: float
    max_tokens: int
    enabled: bool


class ToolCreateRequest(BaseModel):
    """Body of ``POST /ai/tools``."""

    organization_id: UUID
    project_id: UUID | None = None
    tool_key: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    tool_kind: ToolKind
    parameters_schema: dict[str, Any] = Field(default_factory=dict)
    required_permission: str | None = Field(default=None, max_length=128)
    is_mutating: bool = False
    enabled: bool = True


class ToolResponse(BaseModel):
    """One registered tool."""

    id: UUID
    organization_id: UUID
    tool_key: str
    name: str
    description: str
    tool_kind: ToolKind
    parameters_schema: dict[str, Any]
    required_permission: str | None
    is_mutating: bool
    enabled: bool


class ToolExecuteRequest(BaseModel):
    """Body of ``POST /ai/tools/execute``."""

    organization_id: UUID
    project_id: UUID | None = None
    tool_key: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)
    agent_id: UUID | None = None
    caller_permissions: list[str] = Field(default_factory=list)
    allow_mutating: bool = False


class ToolExecuteResponse(BaseModel):
    """What one direct tool execution produced."""

    tool_call_id: UUID
    status: str
    succeeded: bool
    result: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None
    denial_reason: str | None = None


class ModelProviderResponse(BaseModel):
    """One configured model provider."""

    provider: ModelProvider
    is_default: bool


class ModelSelectRequest(BaseModel):
    """Body of ``POST /ai/models/select``."""

    organization_id: UUID
    agent_id: UUID
    provider: ModelProvider
    model: str = Field(min_length=1, max_length=128)


__all__ = [
    "AgentCreateRequest",
    "AgentResponse",
    "ModelProviderResponse",
    "ModelSelectRequest",
    "ToolCreateRequest",
    "ToolExecuteRequest",
    "ToolExecuteResponse",
    "ToolResponse",
]
