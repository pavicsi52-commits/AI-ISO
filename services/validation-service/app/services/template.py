"""Validation template CRUD. Per docs/043 "VALIDATION PROFILES"
"Reusable Templates" -- a template is a starting point copied into a
new profile at creation time; it is never executed itself.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.enums import ValidationProfileType
from app.models.validation_template import ValidationTemplate
from app.repositories.validation_template import ValidationTemplateRepository


class ValidationTemplateService:
    """Creates and reads validation templates."""

    def __init__(self, templates: ValidationTemplateRepository) -> None:
        self._templates = templates

    async def get_by_id(self, template_id: UUID) -> ValidationTemplate:
        """Return the template identified by *template_id*.

        Raises:
            NotFoundError: If no such template exists.
        """
        return await self._templates.require_by_id(template_id)

    async def list_for_org(self, organization_id: UUID) -> list[ValidationTemplate]:
        """Every validation template belonging to *organization_id*."""
        return await self._templates.list_for_org(organization_id)

    async def create(
        self,
        *,
        organization_id: UUID,
        name: str,
        description: str | None,
        profile_type: ValidationProfileType,
        template_content: dict[str, Any],
        authored_by: str | None,
    ) -> ValidationTemplate:
        """Create a new reusable validation template."""
        return await self._templates.create(
            ValidationTemplate(
                organization_id=organization_id,
                name=name,
                description=description,
                profile_type=profile_type,
                template_content=template_content,
                authored_by=authored_by,
            )
        )


__all__ = ["ValidationTemplateService"]
