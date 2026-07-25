"""Project template management. Per docs/034 "PROJECT TEMPLATES": reusable
project templates, Template Versioning. See
``app/models/project_template.py``'s own docstring for why templates
are organization-scoped rather than project-scoped.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from shared_core.exceptions.conflict import ConflictError

from app.models.enums import ProjectTemplateCategory
from app.models.project_template import ProjectTemplate
from app.repositories.project_template import ProjectTemplateRepository


class ProjectTemplateService:
    """Creates and lists reusable, versioned project templates."""

    def __init__(self, templates: ProjectTemplateRepository) -> None:
        self._templates = templates

    async def list_for_org(self, organization_id: UUID) -> list[ProjectTemplate]:
        """Every template available to *organization_id*."""
        return await self._templates.list_for_org(organization_id)

    async def create(
        self,
        organization_id: UUID,
        *,
        name: str,
        description: str | None,
        category: ProjectTemplateCategory,
        template_version: str,
        definition: dict[str, Any],
    ) -> ProjectTemplate:
        """Create a new template version ("Create", "Template Versioning").

        Raises:
            ConflictError: If this exact *name*/*template_version* pair
                already exists for *organization_id*.
        """
        existing = await self._templates.get_by_name_version(
            organization_id, name, template_version
        )
        if existing is not None:
            raise ConflictError(f"Template {name!r} version {template_version!r} already exists.")
        return await self._templates.create(
            ProjectTemplate(
                organization_id=organization_id,
                name=name,
                description=description,
                category=category,
                template_version=template_version,
                definition=definition,
            )
        )


__all__ = ["ProjectTemplateService"]
