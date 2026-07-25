"""User custom-metadata management. Per docs/031 "USER METADATA"."""

from __future__ import annotations

from uuid import UUID

from app.constants import DEFAULT_ORGANIZATION_ID
from app.models.metadata import UserMetadataEntry
from app.repositories.metadata import UserMetadataRepository


class UserMetadataService:
    """Sets, lists, and removes admin-defined custom metadata for a user."""

    def __init__(self, metadata: UserMetadataRepository) -> None:
        self._metadata = metadata

    async def set(self, user_id: UUID, key: str, value: str) -> UserMetadataEntry:
        """Create or overwrite *user_id*'s metadata entry for *key* ("Metadata Updates")."""
        existing = await self._metadata.get_by_key(user_id, key)
        if existing is not None:
            existing.value = value
            return existing
        return await self._metadata.create(
            UserMetadataEntry(
                user_id=user_id, key=key, value=value, organization_id=DEFAULT_ORGANIZATION_ID
            )
        )

    async def list_for_user(self, user_id: UUID) -> list[UserMetadataEntry]:
        """Every metadata entry on record for *user_id*."""
        return await self._metadata.list_for_user(user_id)

    async def remove(self, user_id: UUID, key: str) -> None:
        """Remove *user_id*'s metadata entry for *key*, if it exists."""
        existing = await self._metadata.get_by_key(user_id, key)
        if existing is not None:
            await self._metadata.delete(existing.id)


__all__ = ["UserMetadataService"]
