"""Asset tag management. Per docs/036 "TAGS": Multiple Tags, Bulk
Assignment, Filtering, Search, Inheritance.
"""

from __future__ import annotations

from uuid import UUID

from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError

from app.models.asset_tag import AssetTag
from app.repositories.asset_tag import AssetTagRepository


class AssetTagService:
    """Assigns, lists, and removes tags on an asset."""

    def __init__(self, tags: AssetTagRepository) -> None:
        self._tags = tags

    async def list_for_asset(self, asset_id: UUID) -> list[AssetTag]:
        """Every tag assigned to *asset_id*."""
        return await self._tags.list_for_asset(asset_id)

    async def assign(self, asset_id: UUID, *, organization_id: UUID, label: str) -> AssetTag:
        """Assign *label* to *asset_id*.

        Raises:
            ConflictError: If *label* is already assigned.
        """
        if await self._tags.get_by_label(asset_id, label) is not None:
            raise ConflictError(f"Tag {label!r} is already assigned to this asset.")
        return await self._tags.create(
            AssetTag(asset_id=asset_id, organization_id=organization_id, label=label)
        )

    async def assign_many(
        self, asset_id: UUID, *, organization_id: UUID, labels: list[str]
    ) -> list[AssetTag]:
        """Assign every label in *labels* to *asset_id*, skipping any
        already assigned ("Bulk Assignment").
        """
        assigned: list[AssetTag] = []
        for label in labels:
            existing = await self._tags.get_by_label(asset_id, label)
            if existing is not None:
                assigned.append(existing)
                continue
            assigned.append(
                await self._tags.create(
                    AssetTag(asset_id=asset_id, organization_id=organization_id, label=label)
                )
            )
        return assigned

    async def remove(self, asset_id: UUID, tag_id: UUID) -> None:
        """Remove a tag.

        Raises:
            NotFoundError: If no such tag exists for *asset_id*.
        """
        record = await self._tags.require_by_id(tag_id)
        if record.asset_id != asset_id:
            raise NotFoundError(f"Tag '{tag_id}' was not found for this asset.")
        await self._tags.delete(tag_id)


__all__ = ["AssetTagService"]
