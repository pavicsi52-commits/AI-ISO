"""``discovery_classification`` table -- the classification decision
trail for a discovered asset, distinct from
``discovery_assets.classification`` (the asset's *current* value) the
same "current value on entity + separate history table" pattern
``services/inventory-service``'s own status/health/lifecycle history
tables established -- here recording *why* (rule/heuristic/manual) and
with what confidence, not just *what*.
"""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import AssetClassification, ClassifiedBy


class DiscoveryClassificationEntry(BaseModel):
    """One classification decision for a discovered asset."""

    __tablename__ = "discovery_classification"

    discovery_asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("discovery_assets.id", ondelete="CASCADE"), index=True
    )
    classification: Mapped[AssetClassification] = mapped_column(String(24), index=True)
    confidence_score: Mapped[float] = mapped_column(Float, default=1.0)
    classified_by: Mapped[ClassifiedBy] = mapped_column(String(16), default=ClassifiedBy.HEURISTIC)
    rule_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("discovery_rules.id", ondelete="SET NULL"), default=None
    )


__all__ = ["DiscoveryClassificationEntry"]
