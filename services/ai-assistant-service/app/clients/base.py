"""The shared shape every model provider client implements.

Providers differ in wire format but agree on what a chat turn *is*, so
this module defines that neutral shape once and each client translates
to and from its own provider's documented REST API. Nothing here calls
a vendor SDK: every client is plain ``httpx`` against a documented
endpoint, matching how all seven of ``services/alerting-service``'s own
cross-service clients already work, and keeping this service testable
against real documented response shapes without a credential.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from app.models.enums import MessageRole


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """One turn sent to, or received from, a model."""

    role: MessageRole
    content: str
    tool_call_id: str | None = None
    tool_name: str | None = None


@dataclass(frozen=True, slots=True)
class ToolSpecification:
    """One tool offered to the model, in provider-neutral form."""

    name: str
    description: str
    parameters_schema: dict[str, Any]


@dataclass(frozen=True, slots=True)
class RequestedToolCall:
    """A tool invocation the model asked for."""

    call_id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ChatCompletion:
    """What a provider returned for one chat request.

    ``prompt_tokens``/``completion_tokens`` default to zero rather than
    ``None`` because not every provider reports usage; a zero is
    honestly "not reported" and keeps the analytics rollup summable
    without special-casing every provider.
    """

    content: str
    model: str
    provider: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    tool_calls: list[RequestedToolCall] = field(default_factory=list)
    finish_reason: str | None = None


@runtime_checkable
class ModelClient(Protocol):
    """What every provider client must offer.

    A ``Protocol`` rather than an ABC so a plugin-contributed provider
    (via ``shared_core.plugins.ai.AiExtensions``) satisfies it
    structurally without importing this module.
    """

    provider: str

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        tools: list[ToolSpecification] | None = None,
    ) -> ChatCompletion:
        """Send a chat request and return the completion."""
        ...


__all__ = [
    "ChatCompletion",
    "ChatMessage",
    "ModelClient",
    "RequestedToolCall",
    "ToolSpecification",
]
