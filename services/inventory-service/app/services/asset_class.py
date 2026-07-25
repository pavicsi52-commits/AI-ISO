"""Asset class management ("Asset Classification"). No REST surface of
its own -- see ``app/services/category.py``'s identical rationale.
"""

from __future__ import annotations

from uuid import UUID

from shared_core.exceptions.conflict import ConflictError

from app.models.asset_class import AssetClass
from app.repositories.asset_class import AssetClassRepository


class AssetClassService:
    """Creates and lists asset classes nested under a category."""

    def __init__(self, classes: AssetClassRepository) -> None:
        self._classes = classes

    async def list_for_category(self, category_id: UUID) -> list[AssetClass]:
        """Every class nested under *category_id*."""
        return await self._classes.list_for_category(category_id)

    async def create(
        self, *, category_id: UUID, organization_id: UUID, name: str, description: str | None = None
    ) -> AssetClass:
        """Create a new class within *category_id*.

        Raises:
            ConflictError: If *name* is already taken within *category_id*.
        """
        if await self._classes.get_by_name(category_id, name) is not None:
            raise ConflictError(f"Class {name!r} already exists in this category.")
        return await self._classes.create(
            AssetClass(
                category_id=category_id,
                organization_id=organization_id,
                name=name,
                description=description,
            )
        )

    async def delete(self, class_id: UUID) -> None:
        """Delete a class.

        Raises:
            NotFoundError: If no such class exists.
        """
        await self._classes.delete(class_id)


__all__ = ["AssetClassService"]
