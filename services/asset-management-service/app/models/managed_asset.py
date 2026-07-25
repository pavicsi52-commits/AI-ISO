"""``managed_assets`` table -- the asset governance root entity.

Per docs/038 "MANAGED ASSET MODEL": Managed Asset ID, Inventory Asset
ID, Organization ID, Project ID, Business Name, Business Owner,
Technical Owner, Support Team, Vendor, Status, Lifecycle State,
Criticality, Warranty Status, Compliance Status, Risk Score,
Operational Health, Acquisition Date, Retirement Date, Metadata, Tags,
Labels.

Per docs/038's own framing ("Inventory identifies assets. Asset
Management manages assets."), :attr:`inventory_asset_id` correlates
one-to-one against ``inventory-service``'s own ``inventory_assets.id``
-- not a SQL foreign key, since that table lives in a separate
service's database, but enforced unique here so at most one
``ManagedAsset`` governs a given inventory asset.

``business_owner_id``/``technical_owner_id``/``support_team_id`` are
this asset's *primary* holders of those three roles for fast,
join-free listing -- the same "primary pointer plus a fuller
dedicated table" split ``inventory-service``'s own ``Asset.owner_id``
established; the complete, extensible ownership-role history lives in
``asset_owners``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import (
    ComplianceStatus,
    Criticality,
    LifecycleState,
    ManagedAssetStatus,
    OperationalHealth,
    WarrantyStatus,
)


class ManagedAsset(BaseModel):
    """One asset under enterprise operational governance."""

    __tablename__ = "managed_assets"
    __table_args__ = (
        UniqueConstraint("inventory_asset_id", name="uq_managed_asset_inventory_asset"),
    )

    inventory_asset_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    business_name: Mapped[str] = mapped_column(String(255), index=True)
    business_owner_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    technical_owner_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    support_team_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    vendor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("asset_vendors.id", ondelete="SET NULL"), default=None
    )
    status: Mapped[ManagedAssetStatus] = mapped_column(
        String(16), default=ManagedAssetStatus.PLANNED, index=True
    )
    lifecycle_state: Mapped[LifecycleState] = mapped_column(
        String(16), default=LifecycleState.PROVISIONING, index=True
    )
    criticality: Mapped[Criticality] = mapped_column(String(16), default=Criticality.MEDIUM)
    warranty_status: Mapped[WarrantyStatus] = mapped_column(
        String(16), default=WarrantyStatus.UNKNOWN
    )
    compliance_status: Mapped[ComplianceStatus] = mapped_column(
        String(24), default=ComplianceStatus.UNKNOWN
    )
    risk_score: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    operational_health: Mapped[OperationalHealth] = mapped_column(
        String(16), default=OperationalHealth.UNKNOWN, index=True
    )
    acquisition_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    retirement_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    labels: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)


__all__ = ["ManagedAsset"]
