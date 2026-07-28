"""Model provider registry ("MODEL MANAGEMENT": Model Selection
Policies, Fallback Models).

Builds one client per configured provider and resolves a requested
provider to it. Every provider docs/046 names is represented; a
provider with no credential configured is **not** registered at all,
so asking for it fails with a clear "not configured" error rather than
a confusing 401 from the vendor.

Fallback is explicit and bounded: :meth:`chat_with_fallback` tries the
requested provider, then each configured fallback in order, and raises
if all fail -- it never silently downgrades to a different model
without the caller being able to see which one answered, because the
answer records its own ``provider``/``model``.
"""

from __future__ import annotations

from collections.abc import Sequence

import httpx
from shared_core.exceptions.ai import AIError
from shared_core.logging.logger import get_logger

from app.clients.anthropic_client import AnthropicClient
from app.clients.base import ChatCompletion, ChatMessage, ModelClient, ToolSpecification
from app.clients.embedding_client import EmbeddingClient
from app.clients.gemini_client import GeminiClient
from app.clients.ollama_client import OllamaClient
from app.clients.openai_compatible import OpenAiCompatibleClient
from app.config.settings import AiAssistantServiceSettings
from app.embeddings.encoder import BUILTIN_PROVIDER, HashingEncoder
from app.models.enums import ModelProvider

logger = get_logger("app.clients.registry")


def build_model_clients(
    http_client: httpx.AsyncClient, settings: AiAssistantServiceSettings
) -> dict[ModelProvider, ModelClient]:
    """Build one chat client per *configured* provider.

    A hosted provider with an empty API key is skipped: registering it
    would only produce authentication failures at call time, and a
    missing entry gives a far clearer error.
    """
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
            http_client,
            base_url=settings.anthropic_base_url,
            api_key=settings.anthropic_api_key,
        )
    if settings.gemini_api_key:
        clients[ModelProvider.GEMINI] = GeminiClient(
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
    """Resolves providers to clients and applies fallback policy."""

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

    @property
    def available_providers(self) -> list[ModelProvider]:
        """Every provider actually configured, for ``GET /ai/models``."""
        return sorted(self._clients, key=str)

    def get(self, provider: ModelProvider) -> ModelClient:
        """Return the client for *provider*.

        Raises:
            AIError: If that provider is not configured.
        """
        client = self._clients.get(provider)
        if client is None:
            raise AIError(
                f"Model provider {str(provider)!r} is not configured. Available: "
                f"{[str(name) for name in self.available_providers]}."
            )
        return client

    async def chat_with_fallback(
        self,
        messages: list[ChatMessage],
        *,
        provider: ModelProvider | None = None,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        tools: list[ToolSpecification] | None = None,
    ) -> ChatCompletion:
        """Try the requested provider, then each fallback in order.

        Raises:
            AIError: If every attempted provider failed. The error names
                the whole chain rather than only the last failure, so a
                misconfiguration is diagnosable from one message.
        """
        chosen = provider or self._default_provider
        chain = [chosen, *(p for p in self._fallback_providers if p != chosen)]
        failures: list[str] = []

        for candidate in chain:
            client = self._clients.get(candidate)
            if client is None:
                failures.append(f"{candidate!s}: not configured")
                continue
            try:
                return await client.chat(
                    messages,
                    model=model or self._default_model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    tools=tools,
                )
            except AIError as exc:
                logger.warning(
                    "Model provider failed; trying next in fallback chain.",
                    extra={"extra_fields": {"provider": str(candidate), "error": str(exc)}},
                )
                failures.append(f"{candidate!s}: {exc}")

        raise AIError("Every model provider in the fallback chain failed: " + "; ".join(failures))


def build_embedding_client(
    http_client: httpx.AsyncClient, settings: AiAssistantServiceSettings, provider: str
) -> EmbeddingClient | None:
    """Build the embedding client for *provider*, or ``None`` for ``local``.

    ``None`` is not a failure: it is how the caller learns to use
    :class:`~app.embeddings.encoder.HashingEncoder` instead of a
    network call.
    """
    if provider == BUILTIN_PROVIDER:
        return None
    if provider == str(ModelProvider.OLLAMA):
        return EmbeddingClient(
            http_client,
            base_url=settings.ollama_base_url,
            api_key="",
            provider=provider,
            ollama_style=True,
        )
    if provider == str(ModelProvider.OPENAI):
        return EmbeddingClient(
            http_client,
            base_url=settings.openai_base_url,
            api_key=settings.openai_api_key,
            provider=provider,
        )
    if provider in (str(ModelProvider.VLLM), str(ModelProvider.LOCAL)):
        return EmbeddingClient(
            http_client,
            base_url=settings.vllm_base_url,
            api_key=settings.vllm_api_key,
            provider=provider,
        )
    raise AIError(f"Embedding provider {provider!r} is not supported.")


def build_local_encoder(settings: AiAssistantServiceSettings) -> HashingEncoder:
    """The offline encoder, sized to the configured embedding width."""
    return HashingEncoder(settings.embedding_dimensions)


__all__ = [
    "ModelRegistry",
    "build_embedding_client",
    "build_local_encoder",
    "build_model_clients",
]
