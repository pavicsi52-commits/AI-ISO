"""Playbook categories. Per docs/041 "REPOSITORY" "Support": Categories."""

from __future__ import annotations

from uuid import UUID

from app.models.playbook_category import PlaybookCategory
from app.repositories.playbook_category import PlaybookCategoryRepository


class PlaybookCategoryService:
    """Creates, reads, and deletes playbook categories."""

    def __init__(self, categories: PlaybookCategoryRepository) -> None:
        self._categories = categories

    async def get_by_id(self, category_id: UUID) -> PlaybookCategory:
        """Return the category identified by *category_id*.

        Raises:
            NotFoundError: If no such category exists.
        """
        return await self._categories.require_by_id(category_id)

    async def list_for_org(self, organization_id: UUID) -> list[PlaybookCategory]:
        """Every category belonging to *organization_id*."""
        return await self._categories.list_for_org(organization_id)

    async def create(
        self, *, organization_id: UUID, name: str, description: str | None
    ) -> PlaybookCategory:
        """Define a new playbook category."""
        return await self._categories.create(
            PlaybookCategory(organization_id=organization_id, name=name, description=description)
        )

    async def delete(self, category_id: UUID) -> None:
        """Soft-delete a playbook category."""
        await self._categories.delete(category_id)


__all__ = ["PlaybookCategoryService"]
