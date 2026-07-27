"""Read access to a completed execution's own weighted score."""

from __future__ import annotations

from uuid import UUID

from app.models.validation_score import ValidationScore
from app.repositories.validation_score import ValidationScoreRepository


class ValidationScoreService:
    """Reads a validation execution's own weighted score."""

    def __init__(self, scores: ValidationScoreRepository) -> None:
        self._scores = scores

    async def get_for_execution(self, execution_id: UUID) -> ValidationScore | None:
        """Return *execution_id*'s own weighted score, or ``None`` if not yet computed."""
        return await self._scores.get_for_execution(execution_id)


__all__ = ["ValidationScoreService"]
