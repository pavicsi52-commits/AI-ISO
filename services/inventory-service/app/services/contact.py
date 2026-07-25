"""Asset contact management -- reachable contact persons for an asset."""

from __future__ import annotations

from uuid import UUID

from app.models.asset_contact import AssetContact
from app.repositories.asset_contact import AssetContactRepository


class AssetContactService:
    """Adds, lists, and removes contact persons on an asset."""

    def __init__(self, contacts: AssetContactRepository) -> None:
        self._contacts = contacts

    async def list_for_asset(self, asset_id: UUID) -> list[AssetContact]:
        """Every contact person associated with *asset_id*."""
        return await self._contacts.list_for_asset(asset_id)

    async def add(
        self,
        asset_id: UUID,
        *,
        organization_id: UUID,
        name: str,
        email: str | None = None,
        phone: str | None = None,
        role: str | None = None,
    ) -> AssetContact:
        """Add a contact person to *asset_id*."""
        return await self._contacts.create(
            AssetContact(
                asset_id=asset_id,
                organization_id=organization_id,
                name=name,
                email=email,
                phone=phone,
                role=role,
            )
        )

    async def remove(self, contact_id: UUID) -> None:
        """Remove a contact person.

        Raises:
            NotFoundError: If no such contact exists.
        """
        await self._contacts.delete(contact_id)


__all__ = ["AssetContactService"]
