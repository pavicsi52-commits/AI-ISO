"""Reusable automation content templates, per docs/040's REST APIs
list (``GET/POST /automation/templates``).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.automation_template import AutomationTemplate
from app.models.enums import PlaybookType
from app.repositories.automation_template import AutomationTemplateRepository


class AutomationTemplateService:
    """Creates, reads, updates, and deletes reusable automation templates."""

    def __init__(self, templates: AutomationTemplateRepository) -> None:
        self._templates = templates

    async def get_by_id(self, template_id: UUID) -> AutomationTemplate:
        """Return the template identified by *template_id*.

        Raises:
            NotFoundError: If no such template exists.
        """
        return await self._templates.require_by_id(template_id)

    async def list_for_org(
        self, organization_id: UUID, *, playbook_type: PlaybookType | None = None
    ) -> list[AutomationTemplate]:
        """Every template belonging to *organization_id*."""
        return await self._templates.list_for_org(organization_id, playbook_type=playbook_type)

    async def create(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        template_name: str,
        description: str | None,
        playbook_type: PlaybookType,
        content: str,
        variables_schema: dict[str, Any],
    ) -> AutomationTemplate:
        """Define a new reusable automation template."""
        return await self._templates.create(
            AutomationTemplate(
                organization_id=organization_id,
                project_id=project_id,
                template_name=template_name,
                description=description,
                playbook_type=playbook_type,
                content=content,
                variables_schema=variables_schema,
            )
        )

    async def delete(self, template_id: UUID) -> None:
        """Soft-delete a reusable automation template."""
        await self._templates.delete(template_id)


__all__ = ["AutomationTemplateService"]
