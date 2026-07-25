"""Asset location management. Per docs/036 "LOCATIONS": Country,
Region, Site, Building, Floor, Rack, Rack Unit, Room, GPS Coordinates,
Custom Locations.
"""

from __future__ import annotations

from uuid import UUID

from app.models.asset_location import AssetLocation
from app.repositories.asset_location import AssetLocationRepository


class AssetLocationService:
    """Creates and lists asset locations for an organization."""

    def __init__(self, locations: AssetLocationRepository) -> None:
        self._locations = locations

    async def list_for_org(self, organization_id: UUID) -> list[AssetLocation]:
        """Every location defined for *organization_id*."""
        return await self._locations.list_for_org(organization_id)

    async def create(
        self,
        *,
        organization_id: UUID,
        name: str,
        country: str | None = None,
        region: str | None = None,
        site: str | None = None,
        building: str | None = None,
        floor: str | None = None,
        room: str | None = None,
        rack: str | None = None,
        rack_unit: str | None = None,
        gps_latitude: float | None = None,
        gps_longitude: float | None = None,
    ) -> AssetLocation:
        """Create a new location."""
        return await self._locations.create(
            AssetLocation(
                organization_id=organization_id,
                name=name,
                country=country,
                region=region,
                site=site,
                building=building,
                floor=floor,
                room=room,
                rack=rack,
                rack_unit=rack_unit,
                gps_latitude=gps_latitude,
                gps_longitude=gps_longitude,
            )
        )

    async def get_by_id(self, location_id: UUID) -> AssetLocation:
        """Return the location identified by *location_id*.

        Raises:
            NotFoundError: If no such location exists.
        """
        return await self._locations.require_by_id(location_id)

    async def delete(self, location_id: UUID) -> None:
        """Delete a location.

        Raises:
            NotFoundError: If no such location exists.
        """
        await self._locations.delete(location_id)


__all__ = ["AssetLocationService"]
