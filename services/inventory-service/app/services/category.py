"""Asset category management ("Asset Classification"). No REST surface
of its own -- docs/036's own REST list never names a
``/inventory/categories`` endpoint; exists for programmatic
completeness, matching the no-REST-surface sub-resource pattern every
prior AI-IOS service in this build already established.
"""

from __future__ import annotations

from uuid import UUID

from shared_core.exceptions.conflict import ConflictError

from app.models.asset_category import AssetCategory
from app.repositories.asset_category import AssetCategoryRepository


class AssetCategoryService:
    """Creates and lists asset categories for an organization."""

    def __init__(self, categories: AssetCategoryRepository) -> None:
        self._categories = categories

    async def list_for_org(self, organization_id: UUID) -> list[AssetCategory]:
        """Every category defined for *organization_id*."""
        return await self._categories.list_for_org(organization_id)

    async def create(
        self, *, organization_id: UUID, name: str, description: str | None = None
    ) -> AssetCategory:
        """Create a new category.

        Raises:
            ConflictError: If *name* is already taken within *organization_id*.
        """
        if await self._categories.get_by_name(organization_id, name) is not None:
            raise ConflictError(f"Category {name!r} already exists in this organization.")
        return await self._categories.create(
            AssetCategory(organization_id=organization_id, name=name, description=description)
        )

    async def delete(self, category_id: UUID) -> None:
        """Delete a category.

        Raises:
            NotFoundError: If no such category exists.
        """
        await self._categories.delete(category_id)


__all__ = ["AssetCategoryService"]
