"""Dispatch one chat call from an :class:`~app.models.profile.AgentProfile`.

Factored out of :class:`~app.agents.orchestrator.AgentOrchestrator`'s
own dispatch so :mod:`app.reasoning`'s single-agent reasoning loops
share the exact same profile-to-provider resolution rather than
duplicating it -- both need "take this profile's own provider/model/
temperature and make one real chat call," and only the orchestrator
additionally resolves *which* agent's profile to use.
"""

from __future__ import annotations

from app.clients.base import ChatCompletion, ChatMessage, ToolSpecification
from app.clients.registry import ModelRegistry
from app.models.enums import ModelProvider, RoutingStrategy
from app.models.profile import AgentProfile


async def dispatch_chat(
    registry: ModelRegistry,
    profile: AgentProfile,
    messages: list[ChatMessage],
    *,
    tools: list[ToolSpecification] | None = None,
) -> ChatCompletion:
    """Send *messages* using *profile*'s own provider/model/temperature.

    Coerces ``model_provider``/``routing_strategy`` back to their own
    enum type first -- both are a plain ``str`` at runtime once loaded
    from the database, per this platform's established "enum-as-str"
    convention.

    Raises:
        AIError: If every provider in *profile*'s resolved routing
            chain fails. See :meth:`ModelRegistry.chat`.
    """
    provider = profile.model_provider
    if not isinstance(provider, ModelProvider):
        provider = ModelProvider(provider)
    strategy = profile.routing_strategy
    if not isinstance(strategy, RoutingStrategy):
        strategy = RoutingStrategy(strategy)

    return await registry.chat(
        messages,
        strategy=strategy,
        provider=provider,
        model=profile.model_name,
        temperature=profile.temperature,
        max_tokens=profile.max_tokens,
        tools=tools,
    )


__all__ = ["dispatch_chat"]
