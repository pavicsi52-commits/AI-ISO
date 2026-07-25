"""``asset_budget`` table -- one fiscal-year budget allocation tracked
against a managed asset's costs, supporting docs/038 "COST MANAGEMENT"
spend-vs-budget tracking (docs/038 names the table without further
elaboration).
"""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class AssetBudget(BaseModel):
    """One fiscal-year budget allocation for a managed asset."""

    __tablename__ = "asset_budget"
    __table_args__ = (
        UniqueConstraint(
            "managed_asset_id", "fiscal_year", name="uq_asset_budget_managed_asset_year"
        ),
    )

    managed_asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("managed_assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    fiscal_year: Mapped[int] = mapped_column(Integer, index=True)
    allocated_amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    spent_amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    currency: Mapped[str] = mapped_column(String(8), default="USD")


__all__ = ["AssetBudget"]
