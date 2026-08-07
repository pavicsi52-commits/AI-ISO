"""Model provider registry (docs/060 "MODEL ROUTING").

Builds one client per *configured* provider and resolves a routing
strategy (see :mod:`app.routing.engine`) to a try-in-order chain before
ever making a network call. A provider with no credential configured is
**not** registered at all, so asking for it fails with a clear "not
configured" error rather than a confusing 401 from the vendor -- the
same precedent ``ai-assistant-service``'s own ``app/clients/registry.py``
(Prompt 046) already established.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import httpx
from shared_core.exceptions.ai import AIError
from shared_core.logging.logger import get_logger

from app.clients.anthropic_client import AnthropicClient
from app.clients.base import ChatCompletion, ChatMessage, ModelClient, ToolSpecification
from app.clients.gemini_client import GeminiClient
from app.clients.ollama_client import OllamaClient
from app.clients.openai_compatible import OpenAiCompatibleClient
from app.config.settings import AiAgentPlatformServiceSettings
from app.models.enums import ModelProvider, RoutingStrategy
from app.routing.engine import ProviderCost, resolve_order

logger = get_logger("app.clients.registry")


def build_model_clients(
    http_client: httpx.AsyncClient, settings: AiAgentPlatformServiceSettings
) -> dict[ModelProvider, ModelClient]:
    """Build one chat client per *configured* provider."""
    clients: dict[ModelProvider, ModelClient] = {}

    if settings.openai_api_key:
        clients[ModelProvider.OPENAI] = OpenAiCompatibleClient(
            http_client,
            base_url=settings.openai_base_url,
            api_key=settings.openai_api_key,
            provider=str(ModelProvider.OPENAI),
        )
    if settings.azure_openai_api_key and settings.azure_openai_base_url:
        clients[ModelProvider.AZURE_OPENAI] = OpenAiCompatibleClient(
            http_client,
            base_url=settings.azure_openai_base_url,
            api_key=settings.azure_openai_api_key,
            provider=str(ModelProvider.AZURE_OPENAI),
            api_version="2024-02-01",
        )
    if settings.anthropic_api_key:
        clients[ModelProvider.ANTHROPIC] = AnthropicClient(
            http_client, base_url=settings.anthropic_base_url, api_key=settings.anthropic_api_key
        )
    if settings.gemini_api_key:
        clients[ModelProvider.GOOGLE_GEMINI] = GeminiClient(
            http_client, base_url=settings.gemini_base_url, api_key=settings.gemini_api_key
        )
    if settings.openrouter_api_key:
        clients[ModelProvider.OPENROUTER] = OpenAiCompatibleClient(
            http_client,
            base_url=settings.openrouter_base_url,
            api_key=settings.openrouter_api_key,
            provider=str(ModelProvider.OPENROUTER),
        )

    # Self-hosted providers need no credential -- reachability is the
    # only requirement, and that is discovered at call time.
    clients[ModelProvider.OLLAMA] = OllamaClient(http_client, base_url=settings.ollama_base_url)
    clients[ModelProvider.VLLM] = OpenAiCompatibleClient(
        http_client,
        base_url=settings.vllm_base_url,
        api_key=settings.vllm_api_key,
        provider=str(ModelProvider.VLLM),
    )
    clients[ModelProvider.LOCAL] = OpenAiCompatibleClient(
        http_client,
        base_url=settings.vllm_base_url,
        api_key=settings.vllm_api_key,
        provider=str(ModelProvider.LOCAL),
    )
    return clients


class ModelRegistry:
    """Resolves a routing strategy to a client chain and calls it."""

    def __init__(
        self,
        clients: dict[ModelProvider, ModelClient],
        *,
        default_provider: ModelProvider,
        default_model: str,
        fallback_providers: Sequence[ModelProvider] = (),
    ) -> None:
        self._clients = clients
        self._default_provider = default_provider
        self._default_model = default_model
        self._fallback_providers = tuple(fallback_providers)
        self._observed_latency_ms: dict[ModelProvider, float] = {}

    @property
    def available_providers(self) -> list[ModelProvider]:
        """Every provider actually configured, for ``GET /agents/models``."""
        return sorted(self._clients, key=str)

    def get(self, provider: ModelProvider) -> ModelClient:
        """Return the client for *provider*.

        Raises:
            AIError: If that provider is not configured.
        """
        client = self._clients.get(provider)
        if client is None:
            raise AIError(
                f"Model provider {provider!s} is not configured. Available: "
                f"{[str(name) for name in self.available_providers]}."
            )
        return client

    def observed_latency_ms(self) -> Mapping[ModelProvider, float]:
        """The most recent observed latency per provider, for latency-aware routing."""
        return dict(self._observed_latency_ms)

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        strategy: RoutingStrategy = RoutingStrategy.FALLBACK,
        provider: ModelProvider | None = None,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        tools: list[ToolSpecification] | None = None,
        costs: Mapping[ModelProvider, ProviderCost] | None = None,
        rules: Sequence[tuple[str, ModelProvider]] = (),
        variables: dict[str, Any] | None = None,
    ) -> ChatCompletion:
        """Resolve *strategy* to a try-in-order chain and call providers
        in that order until one succeeds.

        Raises:
            AIError: If every attempted provider failed. The error names
                the whole chain rather than only the last failure, so a
                misconfiguration is diagnosable from one message.
        """
        chain = resolve_order(
            strategy,
            default_provider=provider or self._default_provider,
            candidates=list(self._clients),
            fallback_providers=self._fallback_providers,
            costs=costs,
            observed_latency_ms=self._observed_latency_ms,
            rules=rules,
            variables=variables,
        )
        failures: list[str] = []

        for candidate in chain:
            client = self._clients.get(candidate)
            if client is None:
                failures.append(f"{candidate!s}: not configured")
                continue
            try:
                completion = await client.chat(
                    messages,
                    model=model or self._default_model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    tools=tools,
                )
            except AIError as exc:
                logger.warning(
                    "Model provider failed; trying next in the resolved chain.",
                    extra={"extra_fields": {"provider": str(candidate), "error": str(exc)}},
                )
                failures.append(f"{candidate!s}: {exc}")
                continue
            self._observed_latency_ms[candidate] = completion.latency_ms
            return completion

        raise AIError(
            f"Every model provider in the {strategy!s} chain failed: " + "; ".join(failures)
        )


__all__ = ["ModelRegistry", "build_model_clients"]
