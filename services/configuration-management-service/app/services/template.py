"""Reusable configuration templates, per docs/039's REST APIs list
(``GET/POST /configurations/templates``).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.configuration_template import ConfigurationTemplate
from app.models.enums import ConfigurationType
from app.repositories.configuration_template import ConfigurationTemplateRepository


class ConfigurationTemplateService:
    """Creates, reads, updates, and deletes reusable configuration templates."""

    def __init__(self, templates: ConfigurationTemplateRepository) -> None:
        self._templates = templates

    async def get_by_id(self, template_id: UUID) -> ConfigurationTemplate:
        """Return the template identified by *template_id*.

        Raises:
            NotFoundError: If no such template exists.
        """
        return await self._templates.require_by_id(template_id)

    async def list_for_org(
        self, organization_id: UUID, *, configuration_type: ConfigurationType | None = None
    ) -> list[ConfigurationTemplate]:
        """Every template belonging to *organization_id*."""
        return await self._templates.list_for_org(
            organization_id, configuration_type=configuration_type
        )

    async def create(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        template_name: str,
        description: str | None,
        configuration_type: ConfigurationType,
        content: str,
        variables_schema: dict[str, Any],
    ) -> ConfigurationTemplate:
        """Define a new reusable configuration template."""
        return await self._templates.create(
            ConfigurationTemplate(
                organization_id=organization_id,
                project_id=project_id,
                template_name=template_name,
                description=description,
                configuration_type=configuration_type,
                content=content,
                variables_schema=variables_schema,
            )
        )

    async def update(
        self,
        template_id: UUID,
        *,
        template_name: str,
        description: str | None,
        configuration_type: ConfigurationType,
        content: str,
        variables_schema: dict[str, Any],
    ) -> ConfigurationTemplate:
        """Replace a template's fields."""
        template = await self.get_by_id(template_id)
        template.template_name = template_name
        template.description = description
        template.configuration_type = configuration_type
        template.content = content
        template.variables_schema = variables_schema
        return await self._templates.update(template)

    async def delete(self, template_id: UUID) -> None:
        """Soft-delete a configuration template."""
        await self._templates.delete(template_id)


__all__ = ["ConfigurationTemplateService"]
