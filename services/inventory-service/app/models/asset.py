"""``inventory_assets`` table -- the asset root entity.

Per docs/036 "ASSET MODEL": Asset ID, Organization ID, Project ID,
Asset Name, Display Name, Hostname, FQDN, IP Address, MAC Address,
Serial Number, Vendor, Manufacturer, Model, Firmware Version,
Operating System, Architecture, Environment, Location, Owner, Status,
Health, Lifecycle State, Criticality, Tags, Labels, Metadata, Created
At, Updated At.

Tags/Labels are their own tables (`asset_tags`/`asset_labels`, one row
per assignment) rather than JSON columns here, matching the "Multiple
Tags"/"Bulk Assignment"/"Filtering" and "Key/Value Labels"/"Namespaces"/
"Selectors" support docs/036 requires -- both need to be queried and
filtered independently of the asset row itself. ``location``/``owner``
are each *also* their own dedicated tables (`asset_locations`/
`asset_owners`) for the fuller multi-dimensional tracking docs/036's
own "LOCATIONS"/"OWNERSHIP" sections require (a location's full
country/region/site/building/floor/rack breakdown, or five distinct
ownership roles per asset); :attr:`location_id`/:attr:`owner_id` here
are only the asset's *primary* location/owner for fast, join-free
listing and search.
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import AssetStatus, AssetType, Criticality, HealthStatus, LifecycleState


class Asset(BaseModel):
    """One managed infrastructure asset."""

    __tablename__ = "inventory_assets"

    name: Mapped[str] = mapped_column(String(255), index=True)
    display_name: Mapped[str | None] = mapped_column(String(255), default=None)
    hostname: Mapped[str | None] = mapped_column(String(255), default=None, index=True)
    fqdn: Mapped[str | None] = mapped_column(String(255), default=None)
    ip_address: Mapped[str | None] = mapped_column(String(64), default=None, index=True)
    mac_address: Mapped[str | None] = mapped_column(String(64), default=None, index=True)
    serial_number: Mapped[str | None] = mapped_column(String(128), default=None, index=True)
    vendor: Mapped[str | None] = mapped_column(String(128), default=None)
    manufacturer: Mapped[str | None] = mapped_column(String(128), default=None)
    model: Mapped[str | None] = mapped_column(String(128), default=None)
    firmware_version: Mapped[str | None] = mapped_column(String(64), default=None)
    operating_system: Mapped[str | None] = mapped_column(String(128), default=None)
    architecture: Mapped[str | None] = mapped_column(String(32), default=None)
    environment: Mapped[str | None] = mapped_column(String(64), default=None)
    asset_type: Mapped[AssetType] = mapped_column(String(32), index=True)
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("asset_categories.id", ondelete="SET NULL"), default=None
    )
    class_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("asset_classes.id", ondelete="SET NULL"), default=None
    )
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("asset_locations.id", ondelete="SET NULL"), default=None
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    status: Mapped[AssetStatus] = mapped_column(
        String(16), default=AssetStatus.DISCOVERED, index=True
    )
    health: Mapped[HealthStatus] = mapped_column(
        String(16), default=HealthStatus.UNKNOWN, index=True
    )
    lifecycle_state: Mapped[LifecycleState] = mapped_column(
        String(16), default=LifecycleState.PLANNED, index=True
    )
    criticality: Mapped[Criticality] = mapped_column(String(16), default=Criticality.MEDIUM)
    current_version: Mapped[int] = mapped_column(Integer, default=1)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)


__all__ = ["Asset"]
