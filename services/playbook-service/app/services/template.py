"""Reusable playbook content templates, per docs/041's own REST APIs
list (``GET/POST /playbooks/templates``).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.enums import ContentType
from app.models.playbook_template import PlaybookTemplate
from app.repositories.playbook_template import PlaybookTemplateRepository


class PlaybookTemplateService:
    """Creates, reads, and deletes reusable playbook content templates."""

    def __init__(self, templates: PlaybookTemplateRepository) -> None:
        self._templates = templates

    async def get_by_id(self, template_id: UUID) -> PlaybookTemplate:
        """Return the template identified by *template_id*.

        Raises:
            NotFoundError: If no such template exists.
        """
        return await self._templates.require_by_id(template_id)

    async def list_for_org(
        self, organization_id: UUID, *, content_type: ContentType | None = None
    ) -> list[PlaybookTemplate]:
        """Every template belonging to *organization_id*."""
        return await self._templates.list_for_org(organization_id, content_type=content_type)

    async def create(
        self,
        *,
        organization_id: UUID,
        template_name: str,
        description: str | None,
        content_type: ContentType,
        content: str,
        variables_schema: dict[str, Any],
    ) -> PlaybookTemplate:
        """Define a new reusable playbook content template."""
        return await self._templates.create(
            PlaybookTemplate(
                organization_id=organization_id,
                template_name=template_name,
                description=description,
                content_type=content_type,
                content=content,
                variables_schema=variables_schema,
            )
        )

    async def delete(self, template_id: UUID) -> None:
        """Soft-delete a reusable playbook content template."""
        await self._templates.delete(template_id)


__all__ = ["PlaybookTemplateService"]
