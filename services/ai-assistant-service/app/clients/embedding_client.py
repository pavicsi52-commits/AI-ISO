"""Embedding generation over a provider's own REST API.

OpenAI, Azure, vLLM, OpenRouter, and local OpenAI-compatible endpoints
all expose ``POST /embeddings`` with the same documented shape, so one
client covers them; Ollama's own ``POST /api/embed`` differs and gets
its own path through the same class rather than a near-duplicate file.

The ``local`` provider does not appear here at all -- it needs no
network and is served by :class:`app.embeddings.encoder.HashingEncoder`.
"""

from __future__ import annotations

from typing import Any

import httpx
from shared_core.exceptions.ai import AIError


class EmbeddingClient:
    """Generates embeddings through a provider's own REST API."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        base_url: str,
        api_key: str,
        provider: str,
        ollama_style: bool = False,
    ) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self.provider = provider
        self._ollama_style = ollama_style

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    async def embed(self, texts: list[str], *, model: str) -> list[list[float]]:
        """Return one vector per input text, in the same order.

        Order matters: callers zip these back onto the chunks they came
        from, so a provider returning them out of order would attach
        every vector to the wrong text. The OpenAI-shaped branch sorts
        by the ``index`` field the API documents for exactly this
        reason rather than trusting arrival order.

        Raises:
            AIError: If the provider is unreachable, rejects the
                request, or returns a different number of vectors than
                texts submitted.
        """
        if not texts:
            return []
        path, payload = self._request(texts, model)
        try:
            response = await self._client.post(
                f"{self._base_url}{path}", json=payload, headers=self._headers()
            )
        except httpx.HTTPError as exc:
            raise AIError(f"{self.provider} embeddings unreachable: {exc}") from exc
        if response.status_code != httpx.codes.OK:
            raise AIError(
                f"{self.provider} embeddings returned HTTP {response.status_code} "
                f"for model {model!r}."
            )

        vectors = self._parse(response.json())
        if len(vectors) != len(texts):
            raise AIError(
                f"{self.provider} returned {len(vectors)} embeddings for {len(texts)} inputs."
            )
        return vectors

    def _request(self, texts: list[str], model: str) -> tuple[str, dict[str, Any]]:
        if self._ollama_style:
            return "/api/embed", {"model": model, "input": texts}
        return "/embeddings", {"model": model, "input": texts}

    def _parse(self, body: dict[str, Any]) -> list[list[float]]:
        if self._ollama_style:
            return [[float(value) for value in vector] for vector in body.get("embeddings") or []]
        entries = body.get("data") or []
        ordered = sorted(entries, key=lambda entry: int(entry.get("index", 0)))
        return [[float(value) for value in entry.get("embedding") or []] for entry in ordered]


__all__ = ["EmbeddingClient"]
