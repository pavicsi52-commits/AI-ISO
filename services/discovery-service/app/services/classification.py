"""Discovery asset classification decision trail. Used internally by
``app/services/discovery_execution.py``; has no REST surface of its own.
"""

from __future__ import annotations

from uuid import UUID

from app.models.discovery_classification import DiscoveryClassificationEntry
from app.models.enums import AssetClassification, ClassifiedBy
from app.repositories.discovery_classification import DiscoveryClassificationRepository


class DiscoveryClassificationService:
    """Records and lists classification decisions for a discovered asset."""

    def __init__(self, classifications: DiscoveryClassificationRepository) -> None:
        self._classifications = classifications

    async def record(
        self,
        discovery_asset_id: UUID,
        *,
        organization_id: UUID,
        classification: AssetClassification,
        confidence_score: float = 1.0,
        classified_by: ClassifiedBy = ClassifiedBy.HEURISTIC,
        rule_id: UUID | None = None,
    ) -> DiscoveryClassificationEntry:
        """Record one classification decision."""
        return await self._classifications.create(
            DiscoveryClassificationEntry(
                discovery_asset_id=discovery_asset_id,
                organization_id=organization_id,
                classification=classification,
                confidence_score=confidence_score,
                classified_by=classified_by,
                rule_id=rule_id,
            )
        )

    async def list_for_asset(self, discovery_asset_id: UUID) -> list[DiscoveryClassificationEntry]:
        """Every classification decision for *discovery_asset_id*, newest first."""
        return await self._classifications.list_for_asset(discovery_asset_id)


__all__ = ["DiscoveryClassificationService"]
