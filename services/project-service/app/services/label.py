"""Project label management -- structured ``key:value`` labels, distinct
from :mod:`app.services.tag`'s free-form tags. See
``app/models/project_label.py``'s own docstring.
"""

from __future__ import annotations

from uuid import UUID

from app.models.project_label import ProjectLabel
from app.repositories.project_label import ProjectLabelRepository


class ProjectLabelService:
    """Sets, lists, and removes a project's structured labels."""

    def __init__(self, labels: ProjectLabelRepository) -> None:
        self._labels = labels

    async def list_for_project(self, project_id: UUID) -> list[ProjectLabel]:
        """Every label assigned to *project_id*."""
        return await self._labels.list_for_project(project_id)

    async def set(
        self,
        project_id: UUID,
        key: str,
        value: str,
        *,
        organization_id: UUID,
        color: str | None = None,
    ) -> ProjectLabel:
        """Set (create or overwrite) one label."""
        existing = await self._labels.get_by_key(project_id, key)
        if existing is not None:
            existing.value = value
            existing.color = color
            return existing
        return await self._labels.create(
            ProjectLabel(
                project_id=project_id,
                organization_id=organization_id,
                key=key,
                value=value,
                color=color,
            )
        )

    async def remove(self, project_id: UUID, key: str) -> None:
        """Remove one label, if present (a no-op otherwise)."""
        existing = await self._labels.get_by_key(project_id, key)
        if existing is not None:
            await self._labels.delete(existing.id)


__all__ = ["ProjectLabelService"]
