"""Asset field-value versioning -- a full snapshot per change, for
diff/rollback. See ``app/models/asset_version.py``'s own docstring for
why this captures plain JSON rather than an encrypted blob.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from shared_core.exceptions.not_found import NotFoundError

from app.models.asset_version import AssetVersion
from app.repositories.asset_version import AssetVersionRepository


class AssetVersionService:
    """Creates and reads an asset's field-value version history."""

    def __init__(self, versions: AssetVersionRepository) -> None:
        self._versions = versions

    async def create_snapshot(
        self,
        asset_id: UUID,
        *,
        organization_id: UUID,
        snapshot: dict[str, Any],
        created_by: UUID | None,
    ) -> AssetVersion:
        """Record a new snapshot of *asset_id*'s current field values."""
        latest = await self._versions.get_latest(asset_id)
        next_number = (latest.version_number + 1) if latest is not None else 1
        return await self._versions.create(
            AssetVersion(
                asset_id=asset_id,
                organization_id=organization_id,
                version_number=next_number,
                snapshot=snapshot,
                created_by=created_by,
            )
        )

    async def get_by_number(self, asset_id: UUID, version_number: int) -> AssetVersion:
        """Return *asset_id*'s version identified by *version_number*.

        Raises:
            NotFoundError: If no such version exists.
        """
        version = await self._versions.get_by_number(asset_id, version_number)
        if version is None:
            raise NotFoundError(f"Asset '{asset_id}' has no version numbered {version_number}.")
        return version

    async def list_for_asset(self, asset_id: UUID) -> list[AssetVersion]:
        """Every version of *asset_id*, newest first."""
        return await self._versions.list_for_asset(asset_id)


__all__ = ["AssetVersionService"]
