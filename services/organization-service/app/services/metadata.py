"""Organization custom metadata management."""

from __future__ import annotations

from uuid import UUID

from app.models.organization_metadata import OrganizationMetadataEntry
from app.repositories.organization_metadata import OrganizationMetadataRepository


class OrganizationMetadataService:
    """Sets, lists, and removes an organization's custom key/value metadata."""

    def __init__(self, metadata: OrganizationMetadataRepository) -> None:
        self._metadata = metadata

    async def list_for_org(self, organization_id: UUID) -> list[OrganizationMetadataEntry]:
        """Every metadata entry for *organization_id*."""
        return await self._metadata.list_for_org(organization_id)

    async def set(self, organization_id: UUID, key: str, value: str) -> OrganizationMetadataEntry:
        """Set (create or overwrite) one metadata entry."""
        existing = await self._metadata.get_by_key(organization_id, key)
        if existing is not None:
            existing.value = value
            return existing
        return await self._metadata.create(
            OrganizationMetadataEntry(organization_id=organization_id, key=key, value=value)
        )

    async def remove(self, organization_id: UUID, key: str) -> None:
        """Remove one metadata entry, if present (a no-op otherwise)."""
        existing = await self._metadata.get_by_key(organization_id, key)
        if existing is not None:
            await self._metadata.delete(existing.id)


__all__ = ["OrganizationMetadataService"]
