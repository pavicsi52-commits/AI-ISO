"""Asset metadata management -- free-form key/value metadata, distinct
from schema-validated custom attributes (``app/services/attribute.py``).
"""

from __future__ import annotations

from uuid import UUID

from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError

from app.models.asset_metadata import AssetMetadataEntry
from app.repositories.asset_metadata import AssetMetadataRepository


class AssetMetadataService:
    """Sets, lists, and removes metadata entries on an asset."""

    def __init__(self, metadata: AssetMetadataRepository) -> None:
        self._metadata = metadata

    async def list_for_asset(self, asset_id: UUID) -> list[AssetMetadataEntry]:
        """Every metadata entry for *asset_id*."""
        return await self._metadata.list_for_asset(asset_id)

    async def set(
        self, asset_id: UUID, *, organization_id: UUID, key: str, value: str
    ) -> AssetMetadataEntry:
        """Set *key* to *value* on *asset_id*.

        Raises:
            ConflictError: If *key* already exists (use :meth:`update` to change it).
        """
        if await self._metadata.get_by_key(asset_id, key) is not None:
            raise ConflictError(f"Metadata key {key!r} already exists on this asset.")
        return await self._metadata.create(
            AssetMetadataEntry(
                asset_id=asset_id, organization_id=organization_id, key=key, value=value
            )
        )

    async def remove(self, asset_id: UUID, entry_id: UUID) -> None:
        """Remove a metadata entry.

        Raises:
            NotFoundError: If no such entry exists for *asset_id*.
        """
        entry = await self._metadata.require_by_id(entry_id)
        if entry.asset_id != asset_id:
            raise NotFoundError(f"Metadata entry '{entry_id}' was not found for this asset.")
        await self._metadata.delete(entry_id)


__all__ = ["AssetMetadataService"]
