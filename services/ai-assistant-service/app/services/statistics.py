"""AI analytics ("ANALYTICS").

Conversation Count, Tool Usage, Agent Usage, Model Usage, Latency,
Cost, Token Usage, Recommendation Accuracy, Feedback Scores. Computed
on demand and cached, the same shape every prior AI-IOS statistics
service uses.

**Cost is explicitly an estimate.** It is derived from recorded token
counts against a configured price table, not read from any provider's
billing API. The field is named ``estimated_cost_usd`` and a model with
no configured price contributes zero rather than a guessed number --
silently inventing a rate would make the figure worse than useless.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from uuid import UUID

from app.models.ai_statistics import AiStatistics
from app.models.enums import FeedbackRating, RecommendationStatus, ToolCallStatus
from app.repositories.ai_conversation import AiConversationRepository
from app.repositories.ai_feedback import AiFeedbackRepository
from app.repositories.ai_message import AiMessageRepository
from app.repositories.ai_recommendation import AiRecommendationRepository
from app.repositories.ai_statistics import AiStatisticsRepository
from app.repositories.ai_tool_call import AiToolCallRepository

PRICE_TABLE_USD_PER_1K_TOKENS: dict[str, tuple[float, float]] = {
    "gpt-4o": (0.0025, 0.01),
    "gpt-4o-mini": (0.00015, 0.0006),
    "claude-sonnet-4": (0.003, 0.015),
    "claude-haiku-4": (0.0008, 0.004),
    "gemini-1.5-pro": (0.00125, 0.005),
    "gemini-1.5-flash": (0.000075, 0.0003),
}
"""``model -> (prompt, completion)`` USD per 1000 tokens.

Published list prices at time of writing, kept in one visible table
rather than scattered. Self-hosted models (Ollama, vLLM) are absent on
purpose: their marginal token cost is zero, so counting them as free
is accurate rather than a gap.
"""


def estimate_cost(model: str | None, prompt_tokens: int, completion_tokens: int) -> float:
    """Estimate USD cost for one turn.

    Returns ``0.0`` for an unknown or self-hosted model -- an honest
    "not priced" rather than a fabricated rate.
    """
    if not model:
        return 0.0
    rates = PRICE_TABLE_USD_PER_1K_TOKENS.get(model)
    if rates is None:
        return 0.0
    prompt_rate, completion_rate = rates
    return (prompt_tokens / 1000) * prompt_rate + (completion_tokens / 1000) * completion_rate


class AiStatisticsService:
    """Recomputes and reads an organization's cached AI analytics."""

    def __init__(
        self,
        statistics: AiStatisticsRepository,
        conversations: AiConversationRepository,
        messages: AiMessageRepository,
        tool_calls: AiToolCallRepository,
        feedback: AiFeedbackRepository,
        recommendations: AiRecommendationRepository,
    ) -> None:
        self._statistics = statistics
        self._conversations = conversations
        self._messages = messages
        self._tool_calls = tool_calls
        self._feedback = feedback
        self._recommendations = recommendations

    async def get_for_org(self, organization_id: UUID) -> AiStatistics:
        """Return the cached snapshot, recomputing if none exists."""
        existing = await self._statistics.get_for_org(organization_id)
        if existing is not None:
            return existing
        return await self.recompute(organization_id)

    async def recompute(self, organization_id: UUID) -> AiStatistics:
        """Recompute and persist the analytics snapshot."""
        conversations = await self._conversations.list_for_org(organization_id)
        messages = await self._messages.list_for_org(organization_id)
        tool_calls = await self._tool_calls.list_for_org(organization_id)
        feedback = await self._feedback.list_for_org(organization_id)
        recommendations = await self._recommendations.list_for_org(organization_id)

        prompt_tokens = sum(message.prompt_tokens for message in messages)
        completion_tokens = sum(message.completion_tokens for message in messages)
        cost = sum(
            estimate_cost(message.model, message.prompt_tokens, message.completion_tokens)
            for message in messages
        )

        latencies = [message.latency_ms for message in messages if message.latency_ms is not None]

        positive = sum(1 for entry in feedback if entry.rating == FeedbackRating.POSITIVE)
        decided = [
            entry
            for entry in recommendations
            if entry.status
            in (
                RecommendationStatus.ACCEPTED,
                RecommendationStatus.REJECTED,
                RecommendationStatus.APPLIED,
            )
        ]
        accepted = sum(
            1
            for entry in decided
            if entry.status in (RecommendationStatus.ACCEPTED, RecommendationStatus.APPLIED)
        )

        succeeded_calls = [call for call in tool_calls if call.status == ToolCallStatus.SUCCEEDED]

        snapshot_fields = {
            "total_conversations": len(conversations),
            "total_messages": len(messages),
            "total_tool_calls": len(tool_calls),
            "total_prompt_tokens": prompt_tokens,
            "total_completion_tokens": completion_tokens,
            "estimated_cost_usd": round(cost, 6),
            "average_latency_ms": sum(latencies) / len(latencies) if latencies else 0.0,
            "positive_feedback_rate": positive / len(feedback) if feedback else 0.0,
            "recommendation_acceptance_rate": accepted / len(decided) if decided else 0.0,
            "tool_usage": dict(Counter(str(call.tool_id) for call in succeeded_calls)),
            "agent_usage": dict(
                Counter(str(message.provider) for message in messages if message.provider)
            ),
            "model_usage": dict(
                Counter(str(message.model) for message in messages if message.model)
            ),
            "computed_at": datetime.now(UTC),
        }

        existing = await self._statistics.get_for_org(organization_id)
        if existing is not None:
            for field, value in snapshot_fields.items():
                setattr(existing, field, value)
            return await self._statistics.update(existing)
        return await self._statistics.create(
            AiStatistics(organization_id=organization_id, **snapshot_fields)
        )


__all__ = ["PRICE_TABLE_USD_PER_1K_TOKENS", "AiStatisticsService", "estimate_cost"]
