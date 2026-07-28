"""Recommendation generation and review (docs/046's own AUTOMATION /
VALIDATION / MONITORING / CONFIGURATION assistance sections).

A recommendation about production infrastructure is only useful if an
operator can judge it, so every one carries its own rationale and the
citations it was drawn from -- never a bare conclusion. Acceptance is
an explicit human decision recorded against the row, which is also
what makes "Recommendation Accuracy" measurable later.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from shared_core.exceptions.conflict import ConflictError

from app.events.ai_events import RecommendationGeneratedEvent
from app.models.ai_recommendation import AiRecommendation
from app.models.enums import RecommendationStatus, RecommendationType
from app.repositories.ai_recommendation import AiRecommendationRepository
from app.types import EventPublisher

_DECIDABLE = (RecommendationStatus.PROPOSED,)
"""Only a proposed recommendation may be accepted or rejected.

Re-deciding one already actioned would silently rewrite the record an
audit depends on.
"""


class RecommendationService:
    """Creates and reviews recommendations."""

    def __init__(
        self, recommendations: AiRecommendationRepository, *, publish_event: EventPublisher
    ) -> None:
        self._recommendations = recommendations
        self._publish_event = publish_event

    async def get_by_id(self, recommendation_id: UUID) -> AiRecommendation:
        """Return one recommendation.

        Raises:
            NotFoundError: If no such recommendation exists.
        """
        return await self._recommendations.require_by_id(recommendation_id)

    async def list_for_org(self, organization_id: UUID) -> list[AiRecommendation]:
        """Every recommendation for *organization_id*."""
        return await self._recommendations.list_for_org(organization_id)

    async def list_for_conversation(self, conversation_id: UUID) -> list[AiRecommendation]:
        """Every recommendation generated within one conversation."""
        return await self._recommendations.list_for_conversation(conversation_id)

    async def create(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        conversation_id: UUID | None,
        recommendation_type: RecommendationType,
        title: str,
        body: str,
        rationale: str | None,
        citations: list[dict[str, Any]] | None = None,
        confidence: float | None = None,
    ) -> AiRecommendation:
        """Record a generated recommendation."""
        record = await self._recommendations.create(
            AiRecommendation(
                organization_id=organization_id,
                project_id=project_id,
                conversation_id=conversation_id,
                recommendation_type=recommendation_type,
                title=title,
                body=body,
                rationale=rationale,
                citations=citations or [],
                confidence=confidence,
                status=RecommendationStatus.PROPOSED,
            )
        )
        await self._publish_event(
            RecommendationGeneratedEvent(
                source_service="ai-assistant-service",
                payload={
                    "recommendation_id": str(record.id),
                    "recommendation_type": str(recommendation_type),
                    "title": title,
                },
            )
        )
        return record

    async def decide(
        self, recommendation_id: UUID, *, accept: bool, decided_by: UUID | None
    ) -> AiRecommendation:
        """Accept or reject a proposed recommendation.

        Raises:
            NotFoundError: If no such recommendation exists.
            ConflictError: If it has already been decided.
        """
        recommendation = await self._recommendations.require_by_id(recommendation_id)
        current = (
            recommendation.status
            if isinstance(recommendation.status, RecommendationStatus)
            else RecommendationStatus(recommendation.status)
        )
        if current not in _DECIDABLE:
            raise ConflictError(
                f"Recommendation {recommendation_id!r} is already {str(current)!r} "
                "and cannot be decided again."
            )
        recommendation.status = (
            RecommendationStatus.ACCEPTED if accept else RecommendationStatus.REJECTED
        )
        recommendation.decided_by = decided_by
        return await self._recommendations.update(recommendation)

    async def mark_applied(self, recommendation_id: UUID) -> AiRecommendation:
        """Record that an accepted recommendation was actually applied.

        Raises:
            NotFoundError: If no such recommendation exists.
            ConflictError: If it was never accepted -- applying a
                rejected or unreviewed recommendation would bypass the
                review gate entirely.
        """
        recommendation = await self._recommendations.require_by_id(recommendation_id)
        current = (
            recommendation.status
            if isinstance(recommendation.status, RecommendationStatus)
            else RecommendationStatus(recommendation.status)
        )
        if current is not RecommendationStatus.ACCEPTED:
            raise ConflictError(
                f"Recommendation {recommendation_id!r} is {str(current)!r}; only an "
                "accepted recommendation can be marked applied."
            )
        recommendation.status = RecommendationStatus.APPLIED
        return await self._recommendations.update(recommendation)


__all__ = ["RecommendationService"]
