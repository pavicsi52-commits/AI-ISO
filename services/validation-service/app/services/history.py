"""Per-target historical trend snapshots, backing "Asset Health Trends"."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.models.enums import ValidationExecutionStatus
from app.models.validation_history import ValidationHistory
from app.repositories.validation_history import ValidationHistoryRepository


class ValidationHistoryService:
    """Records and reads per-target historical validation snapshots."""

    def __init__(self, history: ValidationHistoryRepository) -> None:
        self._history = history

    async def list_for_target(self, target_id: UUID) -> list[ValidationHistory]:
        """Every historical snapshot for *target_id*, oldest first."""
        return await self._history.list_for_target(target_id)

    async def record(
        self,
        *,
        organization_id: UUID,
        target_id: UUID,
        execution_id: UUID,
        status: ValidationExecutionStatus,
        score: float | None,
    ) -> ValidationHistory:
        """Record one historical snapshot for a target."""
        return await self._history.create(
            ValidationHistory(
                organization_id=organization_id,
                target_id=target_id,
                execution_id=execution_id,
                status=status,
                score=score,
                recorded_at=datetime.now(UTC),
            )
        )


__all__ = ["ValidationHistoryService"]
