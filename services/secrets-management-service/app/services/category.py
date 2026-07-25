"""Secret categories ("SECRET MODEL": Category). No REST surface of its
own -- exists for programmatic completeness, matching
``services/project-service``'s identical no-REST-surface sub-resource
services.
"""

from __future__ import annotations

from uuid import UUID

from shared_core.exceptions.conflict import ConflictError

from app.models.secret_category import SecretCategory
from app.repositories.secret_category import SecretCategoryRepository


class SecretCategoryService:
    """Creates and lists secret categories for an organization."""

    def __init__(self, categories: SecretCategoryRepository) -> None:
        self._categories = categories

    async def list_for_org(self, organization_id: UUID) -> list[SecretCategory]:
        """Every category defined for *organization_id*."""
        return await self._categories.list_for_org(organization_id)

    async def create(
        self, *, organization_id: UUID, name: str, description: str | None = None
    ) -> SecretCategory:
        """Create a new category.

        Raises:
            ConflictError: If *name* is already taken within *organization_id*.
        """
        if await self._categories.get_by_name(organization_id, name) is not None:
            raise ConflictError(f"Category {name!r} already exists in this organization.")
        return await self._categories.create(
            SecretCategory(organization_id=organization_id, name=name, description=description)
        )

    async def delete(self, category_id: UUID) -> None:
        """Delete a category.

        Raises:
            NotFoundError: If no such category exists.
        """
        await self._categories.delete(category_id)


__all__ = ["SecretCategoryService"]
