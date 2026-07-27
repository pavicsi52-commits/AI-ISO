"""Validation category CRUD -- groups checks under one validation type."""

from __future__ import annotations

from uuid import UUID

from app.models.enums import ValidationType
from app.models.validation_category import ValidationCategory
from app.repositories.validation_category import ValidationCategoryRepository


class ValidationCategoryService:
    """Creates and reads validation categories."""

    def __init__(self, categories: ValidationCategoryRepository) -> None:
        self._categories = categories

    async def get_by_id(self, category_id: UUID) -> ValidationCategory:
        """Return the category identified by *category_id*.

        Raises:
            NotFoundError: If no such category exists.
        """
        return await self._categories.require_by_id(category_id)

    async def list_for_org(self, organization_id: UUID) -> list[ValidationCategory]:
        """Every validation category belonging to *organization_id*."""
        return await self._categories.list_for_org(organization_id)

    async def create(
        self,
        *,
        organization_id: UUID,
        name: str,
        description: str | None,
        validation_type: ValidationType,
    ) -> ValidationCategory:
        """Create a new validation category."""
        return await self._categories.create(
            ValidationCategory(
                organization_id=organization_id,
                name=name,
                description=description,
                validation_type=validation_type,
            )
        )


__all__ = ["ValidationCategoryService"]
