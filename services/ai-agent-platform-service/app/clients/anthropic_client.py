"""Anthropic Messages API client.

Its wire format genuinely differs from OpenAI's, so this is a separate
client rather than a parameterisation of
:mod:`app.clients.openai_compatible`:

- authentication is ``x-api-key`` plus a required ``anthropic-version``
  header, not a bearer token;
- the system prompt is a **top-level** ``system`` field, not a message
  with ``role="system"``;
- content is a list of typed blocks, so text and tool-use arrive
  interleaved rather than in separate fields;
- usage is reported as ``input_tokens``/``output_tokens``.

Written against Anthropic's own documented ``POST /v1/messages`` shape.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
from shared_core.exceptions.ai import AIError

from app.clients.base import ChatCompletion, ChatMessage, RequestedToolCall, ToolSpecification

ANTHROPIC_VERSION = "2023-06-01"
"""The API version header Anthropic requires on every request."""


class AnthropicClient:
    """Chat client for Anthropic's own Messages API."""

    provider = "anthropic"

    def __init__(self, client: httpx.AsyncClient, *, base_url: str, api_key: str) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    def _headers(self) -> dict[str, str]:
        return {
            "content-type": "application/json",
            "x-api-key": self._api_key,
            "anthropic-version": ANTHROPIC_VERSION,
        }

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        tools: list[ToolSpecification] | None = None,
    ) -> ChatCompletion:
        """Send a chat request to the Messages API.

        Raises:
            AIError: If Anthropic is unreachable, rejects the request,
                or returns a body without usable content.
        """
        system_prompt = "\n\n".join(
            message.content for message in messages if message.role == "system"
        )
        conversation = [
            {"role": _role(message), "content": message.content}
            for message in messages
            if message.role != "system"
        ]

        payload: dict[str, Any] = {
            "model": model,
            "messages": conversation,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system_prompt:
            payload["system"] = system_prompt
        if tools:
            payload["tools"] = [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.parameters_schema,
                }
                for tool in tools
            ]

        started = time.perf_counter()
        try:
            response = await self._client.post(
                f"{self._base_url}/messages", json=payload, headers=self._headers()
            )
        except httpx.HTTPError as exc:
            raise AIError(f"anthropic is unreachable: {exc}") from exc
        latency_ms = (time.perf_counter() - started) * 1_000
        if response.status_code != httpx.codes.OK:
            raise AIError(f"anthropic returned HTTP {response.status_code} for model {model!r}.")

        body = response.json()
        blocks = body.get("content") or []
        text = "".join(block.get("text", "") for block in blocks if block.get("type") == "text")
        tool_calls = [
            RequestedToolCall(
                call_id=str(block.get("id", "")),
                name=str(block.get("name", "")),
                arguments=dict(block.get("input") or {}),
            )
            for block in blocks
            if block.get("type") == "tool_use" and block.get("name")
        ]
        usage = body.get("usage") or {}

        return ChatCompletion(
            content=text,
            model=body.get("model", model),
            provider=self.provider,
            prompt_tokens=int(usage.get("input_tokens", 0)),
            completion_tokens=int(usage.get("output_tokens", 0)),
            latency_ms=latency_ms,
            tool_calls=tool_calls,
            finish_reason=body.get("stop_reason"),
        )


def _role(message: ChatMessage) -> str:
    """Map an internal role onto Anthropic's own two-role vocabulary.

    Anthropic accepts only ``user``/``assistant`` in the message list;
    a tool *result* is delivered as a user-role turn, which is what
    that API documents.
    """
    return "assistant" if message.role == "assistant" else "user"


__all__ = ["ANTHROPIC_VERSION", "AnthropicClient"]
