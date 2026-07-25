"""Asset ownership management. Per docs/036 "OWNERSHIP": Business
Owner, Technical Owner, Support Team, Vendor, Department.
"""

from __future__ import annotations

from uuid import UUID

from shared_core.exceptions.not_found import NotFoundError

from app.models.asset_owner import AssetOwner
from app.models.enums import OwnerType
from app.repositories.asset_owner import AssetOwnerRepository


class AssetOwnerService:
    """Assigns and lists ownership-role assignments on an asset."""

    def __init__(self, owners: AssetOwnerRepository) -> None:
        self._owners = owners

    async def list_for_asset(self, asset_id: UUID) -> list[AssetOwner]:
        """Every ownership-role assignment on *asset_id*."""
        return await self._owners.list_for_asset(asset_id)

    async def assign(
        self,
        asset_id: UUID,
        *,
        organization_id: UUID,
        owner_type: OwnerType,
        principal_id: UUID | None = None,
        name: str | None = None,
    ) -> AssetOwner:
        """Assign (or replace) *asset_id*'s owner for *owner_type*."""
        existing = await self._owners.get_for_role(asset_id, owner_type)
        if existing is not None:
            existing.principal_id = principal_id
            existing.name = name
            return existing
        return await self._owners.create(
            AssetOwner(
                asset_id=asset_id,
                organization_id=organization_id,
                owner_type=owner_type,
                principal_id=principal_id,
                name=name,
            )
        )

    async def remove(self, asset_id: UUID, assignment_id: UUID) -> None:
        """Remove an ownership-role assignment.

        Raises:
            NotFoundError: If no such assignment exists for *asset_id*.
        """
        record = await self._owners.require_by_id(assignment_id)
        if record.asset_id != asset_id:
            raise NotFoundError(f"Owner assignment '{assignment_id}' was not found for this asset.")
        await self._owners.delete(assignment_id)


__all__ = ["AssetOwnerService"]
