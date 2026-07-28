"""Google Gemini generateContent client.

Another genuinely different wire format:

- the model name is in the **path**, not the body
  (``/models/{model}:generateContent``);
- authentication is an API key query parameter;
- turns are ``contents`` with ``parts``, and the assistant role is
  called ``model`` rather than ``assistant``;
- the system prompt is ``systemInstruction``;
- generation options live under ``generationConfig``;
- usage is ``usageMetadata`` with ``promptTokenCount``/
  ``candidatesTokenCount``.

Written against Google's own documented ``generateContent`` shape.
"""

from __future__ import annotations

from typing import Any

import httpx
from shared_core.exceptions.ai import AIError

from app.clients.base import (
    ChatCompletion,
    ChatMessage,
    RequestedToolCall,
    ToolSpecification,
)
from app.models.enums import MessageRole


class GeminiClient:
    """Chat client for Google's own Gemini generateContent API."""

    provider = "gemini"

    def __init__(self, client: httpx.AsyncClient, *, base_url: str, api_key: str) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        tools: list[ToolSpecification] | None = None,
    ) -> ChatCompletion:
        """Send a chat request to generateContent.

        Raises:
            AIError: If Gemini is unreachable, rejects the request, or
                returns a body without a usable candidate.
        """
        system_prompt = "\n\n".join(
            message.content for message in messages if message.role is MessageRole.SYSTEM
        )
        contents = [
            {"role": _role(message), "parts": [{"text": message.content}]}
            for message in messages
            if message.role is not MessageRole.SYSTEM
        ]

        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        if system_prompt:
            payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}
        if tools:
            payload["tools"] = [
                {
                    "functionDeclarations": [
                        {
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": tool.parameters_schema,
                        }
                        for tool in tools
                    ]
                }
            ]

        try:
            response = await self._client.post(
                f"{self._base_url}/models/{model}:generateContent",
                json=payload,
                params={"key": self._api_key},
                headers={"Content-Type": "application/json"},
            )
        except httpx.HTTPError as exc:
            raise AIError(f"gemini is unreachable: {exc}") from exc
        if response.status_code != httpx.codes.OK:
            raise AIError(f"gemini returned HTTP {response.status_code} for model {model!r}.")

        body = response.json()
        candidates = body.get("candidates") or []
        if not candidates:
            raise AIError(f"gemini returned no candidates for model {model!r}.")
        parts = (candidates[0].get("content") or {}).get("parts") or []
        text = "".join(part.get("text", "") for part in parts if "text" in part)
        tool_calls = [
            RequestedToolCall(
                call_id=str(part["functionCall"].get("name", "")),
                name=str(part["functionCall"].get("name", "")),
                arguments=dict(part["functionCall"].get("args") or {}),
            )
            for part in parts
            if "functionCall" in part and part["functionCall"].get("name")
        ]
        usage = body.get("usageMetadata") or {}

        return ChatCompletion(
            content=text,
            model=model,
            provider=self.provider,
            prompt_tokens=int(usage.get("promptTokenCount", 0)),
            completion_tokens=int(usage.get("candidatesTokenCount", 0)),
            tool_calls=tool_calls,
            finish_reason=candidates[0].get("finishReason"),
        )


def _role(message: ChatMessage) -> str:
    """Gemini names the assistant role ``model``; everything else is ``user``."""
    return "model" if message.role is MessageRole.ASSISTANT else "user"


__all__ = ["GeminiClient"]
