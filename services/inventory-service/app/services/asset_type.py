"""Asset type catalog management. No REST surface of its own -- see
``app/services/category.py``'s identical rationale.
"""

from __future__ import annotations

from uuid import UUID

from shared_core.exceptions.conflict import ConflictError

from app.models.asset_type import AssetTypeDefinition
from app.repositories.asset_type import AssetTypeDefinitionRepository


class AssetTypeDefinitionService:
    """Creates and lists asset type catalog entries for an organization."""

    def __init__(self, types: AssetTypeDefinitionRepository) -> None:
        self._types = types

    async def list_for_org(self, organization_id: UUID) -> list[AssetTypeDefinition]:
        """Every type definition catalogued for *organization_id*."""
        return await self._types.list_for_org(organization_id)

    async def create(
        self,
        *,
        organization_id: UUID,
        code: str,
        name: str,
        description: str | None = None,
        category_id: UUID | None = None,
        icon: str | None = None,
        is_system: bool = False,
    ) -> AssetTypeDefinition:
        """Create a new type catalog entry.

        Raises:
            ConflictError: If *code* is already taken within *organization_id*.
        """
        if await self._types.get_by_code(organization_id, code) is not None:
            raise ConflictError(f"Asset type code {code!r} already exists in this organization.")
        return await self._types.create(
            AssetTypeDefinition(
                organization_id=organization_id,
                code=code,
                name=name,
                description=description,
                category_id=category_id,
                icon=icon,
                is_system=is_system,
            )
        )


__all__ = ["AssetTypeDefinitionService"]
