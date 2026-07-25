"""``asset_contracts`` table. Per docs/038 "CONTRACT MANAGEMENT"
"Support": Support Contracts, Maintenance Contracts, License
Contracts, Vendor Contracts, Contract Expiration, Renewal Tracking,
Documents, Attachments. :attr:`documents` embeds lightweight
attachment metadata (filename/url/uploaded_at) since docs/038 names no
dedicated attachments table.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ContractStatus, ContractType, RenewalStatus


class AssetContract(BaseModel):
    """One contract covering a managed asset."""

    __tablename__ = "asset_contracts"

    managed_asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("managed_assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    vendor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("asset_vendors.id", ondelete="SET NULL"), default=None
    )
    contract_type: Mapped[ContractType] = mapped_column(String(16), index=True)
    status: Mapped[ContractStatus] = mapped_column(
        String(16), default=ContractStatus.PENDING, index=True
    )
    contract_number: Mapped[str | None] = mapped_column(String(128), default=None)
    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    renewal_status: Mapped[RenewalStatus] = mapped_column(
        String(16), default=RenewalStatus.NOT_RENEWED
    )
    documents: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)


__all__ = ["AssetContract"]
