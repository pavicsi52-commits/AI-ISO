"""Model-provider routing strategy resolution (docs/060 "MODEL ROUTING").

A genuine gap beyond ``ai-assistant-service``'s own ``ModelRegistry
.chat_with_fallback`` (Prompt 046), which only ever tries an explicit,
static chain in declaration order -- Rule-based, Cost-aware, and
Latency-aware routing all need to *decide* that order first. This
module is that decision layer: pure, given a policy and whatever
telemetry the caller already has, it never itself makes a network call
-- the actual HTTP request stays in ``app/clients/registry.py``, which
just iterates whatever order this module returns.

Rule-based routing reuses ``shared_core.workflow.conditions
.evaluate_rules``/``Rule`` directly -- the same generic ordered-
condition-to-result evaluator this platform's own workflow engine
already uses for conditional branching, applied here to a provider
selection instead of a graph edge.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from shared_core.workflow.conditions import Rule, evaluate_rules

from app.models.enums import ModelProvider, RoutingStrategy


@dataclass(frozen=True, slots=True)
class ProviderCost:
    """One provider's own cost per 1,000 tokens, in USD."""

    prompt_usd_per_1k: float
    completion_usd_per_1k: float

    @property
    def average_usd_per_1k(self) -> float:
        return (self.prompt_usd_per_1k + self.completion_usd_per_1k) / 2


def order_by_fallback(
    default_provider: ModelProvider, fallback_providers: Sequence[ModelProvider]
) -> list[ModelProvider]:
    """The explicit, static chain every routing strategy falls back to
    when it has nothing better to decide with.
    """
    chain = [default_provider]
    chain.extend(provider for provider in fallback_providers if provider != default_provider)
    return chain


def order_by_cost(
    candidates: Sequence[ModelProvider], costs: Mapping[ModelProvider, ProviderCost]
) -> list[ModelProvider]:
    """Cheapest-first, by average per-1k-token price.

    A candidate with no cost entry sorts last -- an unpriced provider
    is not necessarily free, and treating it as such would silently
    prefer an unmeasured provider over every priced one.
    """

    def _price(provider: ModelProvider) -> float:
        cost = costs.get(provider)
        return cost.average_usd_per_1k if cost is not None else float("inf")

    return sorted(candidates, key=_price)


def order_by_latency(
    candidates: Sequence[ModelProvider], observed_latency_ms: Mapping[ModelProvider, float]
) -> list[ModelProvider]:
    """Fastest-observed-first.

    A candidate never yet observed sorts last -- optimistically
    assuming an unmeasured provider is fast would defeat the point of
    latency-aware routing the first time it actually matters.
    """

    def _latency(provider: ModelProvider) -> float:
        return observed_latency_ms.get(provider, float("inf"))

    return sorted(candidates, key=_latency)


def order_by_rules(
    candidates: Sequence[ModelProvider],
    rules: Sequence[tuple[str, ModelProvider]],
    variables: dict[str, Any],
) -> list[ModelProvider]:
    """Rule-based: the first rule whose condition matches *variables*
    wins, its own provider goes first; every other candidate follows in
    its own given order.
    """
    if not rules:
        return list(candidates)
    rule_objects = [
        Rule(condition=condition, result=str(provider)) for condition, provider in rules
    ]
    matched = evaluate_rules(rule_objects, variables)
    if matched is None:
        return list(candidates)
    winner = ModelProvider(matched)
    return [winner, *(provider for provider in candidates if provider != winner)]


def resolve_order(
    strategy: RoutingStrategy,
    *,
    default_provider: ModelProvider,
    candidates: Sequence[ModelProvider],
    fallback_providers: Sequence[ModelProvider] = (),
    costs: Mapping[ModelProvider, ProviderCost] | None = None,
    observed_latency_ms: Mapping[ModelProvider, float] | None = None,
    rules: Sequence[tuple[str, ModelProvider]] = (),
    variables: dict[str, Any] | None = None,
) -> list[ModelProvider]:
    """Resolve the full try-in-this-order chain for one routing decision.

    Every strategy narrows to *candidates* first (the providers actually
    configured/available right now) -- a strategy never recommends a
    provider the caller didn't offer.
    """
    base_chain = order_by_fallback(default_provider, fallback_providers)
    pool = [provider for provider in base_chain if provider in candidates]
    pool.extend(provider for provider in candidates if provider not in pool)

    if strategy is RoutingStrategy.COST_AWARE:
        return order_by_cost(pool, costs or {})
    if strategy is RoutingStrategy.LATENCY_AWARE:
        return order_by_latency(pool, observed_latency_ms or {})
    if strategy is RoutingStrategy.RULE_BASED:
        return order_by_rules(pool, rules, variables or {})
    return pool


__all__ = [
    "ProviderCost",
    "order_by_cost",
    "order_by_fallback",
    "order_by_latency",
    "order_by_rules",
    "resolve_order",
]
