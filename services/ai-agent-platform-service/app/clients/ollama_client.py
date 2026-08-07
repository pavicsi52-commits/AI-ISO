"""Ollama chat client.

Ollama's own ``POST /api/chat`` is close to OpenAI's but differs enough
to warrant its own client:

- no ``/v1`` prefix and no authentication (it is a local daemon);
- ``stream`` must be sent explicitly as ``false`` or it returns a
  newline-delimited stream that would break a single-JSON parse;
- generation options live under ``options``;
- the reply is a single ``message`` object, not a ``choices`` list;
- usage is ``prompt_eval_count``/``eval_count``.

Written against Ollama's own documented API.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
from shared_core.exceptions.ai import AIError

from app.clients.base import ChatCompletion, ChatMessage, RequestedToolCall, ToolSpecification


class OllamaClient:
    """Chat client for a local or self-hosted Ollama daemon."""

    provider = "ollama"

    def __init__(self, client: httpx.AsyncClient, *, base_url: str) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        tools: list[ToolSpecification] | None = None,
    ) -> ChatCompletion:
        """Send a chat request to Ollama.

        Raises:
            AIError: If Ollama is unreachable, rejects the request, or
                returns a body without a usable message.
        """
        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": message.role, "content": message.content} for message in messages
            ],
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters_schema,
                    },
                }
                for tool in tools
            ]

        started = time.perf_counter()
        try:
            response = await self._client.post(f"{self._base_url}/api/chat", json=payload)
        except httpx.HTTPError as exc:
            raise AIError(f"ollama is unreachable: {exc}") from exc
        latency_ms = (time.perf_counter() - started) * 1_000
        if response.status_code != httpx.codes.OK:
            raise AIError(f"ollama returned HTTP {response.status_code} for model {model!r}.")

        body = response.json()
        message = body.get("message") or {}
        tool_calls = [
            RequestedToolCall(
                call_id=str(raw.get("function", {}).get("name", "")),
                name=str(raw.get("function", {}).get("name", "")),
                arguments=dict(raw.get("function", {}).get("arguments") or {}),
            )
            for raw in (message.get("tool_calls") or [])
            if raw.get("function", {}).get("name")
        ]

        return ChatCompletion(
            content=message.get("content") or "",
            model=body.get("model", model),
            provider=self.provider,
            prompt_tokens=int(body.get("prompt_eval_count", 0)),
            completion_tokens=int(body.get("eval_count", 0)),
            latency_ms=latency_ms,
            tool_calls=tool_calls,
            finish_reason=body.get("done_reason"),
        )


__all__ = ["OllamaClient"]
