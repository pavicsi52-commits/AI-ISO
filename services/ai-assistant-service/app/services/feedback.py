"""User feedback on assistant turns ("ANALYTICS": Feedback Scores)."""

from __future__ import annotations

from uuid import UUID

from app.models.ai_feedback import AiFeedback
from app.models.enums import FeedbackRating
from app.repositories.ai_feedback import AiFeedbackRepository


class FeedbackService:
    """Records and reads feedback on assistant messages."""

    def __init__(self, feedback: AiFeedbackRepository) -> None:
        self._feedback = feedback

    async def list_for_message(self, message_id: UUID) -> list[AiFeedback]:
        """Every rating submitted for one message."""
        return await self._feedback.list_for_message(message_id)

    async def submit(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        message_id: UUID,
        rating: FeedbackRating,
        comment: str | None = None,
        submitted_by: UUID | None = None,
    ) -> AiFeedback:
        """Record one rating.

        Repeated submissions are kept rather than deduplicated: two
        people may legitimately disagree about the same answer, and
        collapsing that would distort the score.
        """
        return await self._feedback.create(
            AiFeedback(
                organization_id=organization_id,
                project_id=project_id,
                message_id=message_id,
                rating=rating,
                comment=comment,
                submitted_by=submitted_by,
            )
        )


__all__ = ["FeedbackService"]
