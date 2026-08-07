"""OpenAI-compatible chat client.

One implementation serves five of the eight providers docs/060 names --
OpenAI, Azure OpenAI, vLLM, OpenRouter, and any "Local Model" behind an
OpenAI-compatible endpoint -- because all five speak the same
documented ``POST /chat/completions`` shape. Writing five near-identical
classes would be duplication, not coverage; the differences that do
exist (auth header, API-version query parameter) are parameters, not
separate code paths.

Anthropic and Gemini get their own clients because their wire formats
genuinely differ; Ollama gets its own because its ``/api/chat`` shape
differs too.
"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx
from shared_core.exceptions.ai import AIError

from app.clients.base import ChatCompletion, ChatMessage, RequestedToolCall, ToolSpecification


def _message_payload(message: ChatMessage) -> dict[str, Any]:
    if message.role == "tool":
        return {
            "role": "tool",
            "content": message.content,
            "tool_call_id": message.tool_call_id or "",
        }
    return {"role": message.role, "content": message.content}


def _tool_payload(tool: ToolSpecification) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters_schema,
        },
    }


class OpenAiCompatibleClient:
    """Chat client for any provider speaking OpenAI's own REST shape."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        base_url: str,
        api_key: str,
        provider: str,
        api_version: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self.provider = provider
        self._api_version = api_version
        self._extra_headers = extra_headers or {}

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", **self._extra_headers}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        tools: list[ToolSpecification] | None = None,
    ) -> ChatCompletion:
        """Send a chat request to an OpenAI-compatible endpoint.

        Raises:
            AIError: If the provider is unreachable, rejects the
                request, or returns a body without a usable choice.
        """
        payload: dict[str, Any] = {
            "model": model,
            "messages": [_message_payload(message) for message in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = [_tool_payload(tool) for tool in tools]

        params = {"api-version": self._api_version} if self._api_version else None
        started = time.perf_counter()
        try:
            response = await self._client.post(
                f"{self._base_url}/chat/completions",
                json=payload,
                headers=self._headers(),
                params=params,
            )
        except httpx.HTTPError as exc:
            raise AIError(f"{self.provider} is unreachable: {exc}") from exc
        latency_ms = (time.perf_counter() - started) * 1_000
        if response.status_code != httpx.codes.OK:
            raise AIError(
                f"{self.provider} returned HTTP {response.status_code} for model {model!r}."
            )

        body = response.json()
        choices = body.get("choices") or []
        if not choices:
            raise AIError(f"{self.provider} returned no choices for model {model!r}.")
        message = choices[0].get("message") or {}
        usage = body.get("usage") or {}

        return ChatCompletion(
            content=message.get("content") or "",
            model=body.get("model", model),
            provider=self.provider,
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
            latency_ms=latency_ms,
            tool_calls=_parse_tool_calls(message.get("tool_calls") or []),
            finish_reason=choices[0].get("finish_reason"),
        )


def _parse_tool_calls(raw_calls: list[dict[str, Any]]) -> list[RequestedToolCall]:
    """Parse the provider's own tool-call block.

    Arguments arrive as a JSON *string*, and a model can emit malformed
    JSON there. A call whose arguments cannot be parsed is dropped
    rather than crashing the whole turn -- the caller then simply
    proceeds without that tool, which is far better than failing the
    whole execution outright.
    """
    calls: list[RequestedToolCall] = []
    for raw in raw_calls:
        function = raw.get("function") or {}
        name = function.get("name")
        if not name:
            continue
        raw_arguments = function.get("arguments") or "{}"
        try:
            arguments = (
                json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments
            )
        except (TypeError, ValueError):
            continue
        if not isinstance(arguments, dict):
            continue
        calls.append(
            RequestedToolCall(call_id=str(raw.get("id", "")), name=str(name), arguments=arguments)
        )
    return calls


__all__ = ["OpenAiCompatibleClient"]
