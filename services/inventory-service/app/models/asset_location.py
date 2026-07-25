"""``asset_locations`` table. Per docs/036 "LOCATIONS": Country, Region,
Site, Building, Floor, Rack, Rack Unit, Room, GPS Coordinates, Custom
Locations. One location may be shared by many assets (a rack holds
many servers), so this is its own referenced table rather than inline
columns on :class:`~app.models.asset.Asset`.
"""

from __future__ import annotations

from shared_core.database.base import BaseModel
from sqlalchemy import Float, String
from sqlalchemy.orm import Mapped, mapped_column


class AssetLocation(BaseModel):
    """One physical (or logical) location an asset can be placed at."""

    __tablename__ = "asset_locations"

    name: Mapped[str] = mapped_column(String(255))
    country: Mapped[str | None] = mapped_column(String(128), default=None)
    region: Mapped[str | None] = mapped_column(String(128), default=None)
    site: Mapped[str | None] = mapped_column(String(128), default=None)
    building: Mapped[str | None] = mapped_column(String(128), default=None)
    floor: Mapped[str | None] = mapped_column(String(32), default=None)
    room: Mapped[str | None] = mapped_column(String(64), default=None)
    rack: Mapped[str | None] = mapped_column(String(64), default=None)
    rack_unit: Mapped[str | None] = mapped_column(String(16), default=None)
    gps_latitude: Mapped[float | None] = mapped_column(Float, default=None)
    gps_longitude: Mapped[float | None] = mapped_column(Float, default=None)


__all__ = ["AssetLocation"]
