"""External discovery correlation management. Per docs/036 "INVENTORY
SYNCHRONIZATION": Discovery Updates. See
``app/models/asset_discovery_link.py``'s own docstring for the scope
boundary against the (out of scope) discovery engine itself.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.models.asset_discovery_link import AssetDiscoveryLink
from app.models.enums import DiscoverySource
from app.repositories.asset_discovery_link import AssetDiscoveryLinkRepository


class AssetDiscoveryLinkService:
    """Records and looks up correlations between assets and external
    discovery records.
    """

    def __init__(self, links: AssetDiscoveryLinkRepository) -> None:
        self._links = links

    async def list_for_asset(self, asset_id: UUID) -> list[AssetDiscoveryLink]:
        """Every discovery correlation recorded for *asset_id*."""
        return await self._links.list_for_asset(asset_id)

    async def record(
        self,
        asset_id: UUID,
        *,
        organization_id: UUID,
        source: DiscoverySource,
        external_id: str,
    ) -> AssetDiscoveryLink:
        """Record (or refresh) a correlation between *asset_id* and an
        external discovery record.
        """
        existing = await self._links.get_by_external_id(source, external_id)
        if existing is not None:
            existing.last_seen_at = datetime.now(UTC)
            return existing
        return await self._links.create(
            AssetDiscoveryLink(
                asset_id=asset_id,
                organization_id=organization_id,
                source=source,
                external_id=external_id,
                last_seen_at=datetime.now(UTC),
            )
        )


__all__ = ["AssetDiscoveryLinkService"]
