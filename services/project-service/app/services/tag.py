"""Project tag management. Per docs/034 "PROJECT TAGS": Custom Tags, Categories."""

from __future__ import annotations

from uuid import UUID

from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError

from app.models.project_tag import ProjectTag
from app.repositories.project_tag import ProjectTagRepository


class ProjectTagService:
    """Assigns, lists, and removes tags on a project."""

    def __init__(self, tags: ProjectTagRepository) -> None:
        self._tags = tags

    async def list_for_project(self, project_id: UUID) -> list[ProjectTag]:
        """Every tag assigned to *project_id*."""
        return await self._tags.list_for_project(project_id)

    async def assign(
        self, project_id: UUID, *, organization_id: UUID, label: str, category: str | None
    ) -> ProjectTag:
        """Assign *label* to *project_id*.

        Raises:
            ConflictError: If *label* is already assigned.
        """
        if await self._tags.get_by_label(project_id, label) is not None:
            raise ConflictError(f"Tag {label!r} is already assigned to this project.")
        return await self._tags.create(
            ProjectTag(
                project_id=project_id,
                organization_id=organization_id,
                label=label,
                category=category,
            )
        )

    async def remove(self, project_id: UUID, tag_id: UUID) -> None:
        """Remove a tag.

        Raises:
            NotFoundError: If no such tag exists for *project_id*.
        """
        record = await self._tags.require_by_id(tag_id)
        if record.project_id != project_id:
            raise NotFoundError(f"Tag '{tag_id}' was not found for this project.")
        await self._tags.delete(tag_id)


__all__ = ["ProjectTagService"]
