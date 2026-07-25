"""Project custom metadata management -- no dedicated REST surface in
docs/034's own endpoint list, matching ``app/services/preferences.py``'s
identical scope decision.
"""

from __future__ import annotations

from uuid import UUID

from app.models.project_metadata import ProjectMetadataEntry
from app.repositories.project_metadata import ProjectMetadataRepository


class ProjectMetadataService:
    """Sets, lists, and removes a project's custom key/value metadata."""

    def __init__(self, metadata: ProjectMetadataRepository) -> None:
        self._metadata = metadata

    async def list_for_project(self, project_id: UUID) -> list[ProjectMetadataEntry]:
        """Every metadata entry for *project_id*."""
        return await self._metadata.list_for_project(project_id)

    async def set(
        self, project_id: UUID, key: str, value: str, *, organization_id: UUID
    ) -> ProjectMetadataEntry:
        """Set (create or overwrite) one metadata entry."""
        existing = await self._metadata.get_by_key(project_id, key)
        if existing is not None:
            existing.value = value
            return existing
        return await self._metadata.create(
            ProjectMetadataEntry(
                project_id=project_id, organization_id=organization_id, key=key, value=value
            )
        )

    async def remove(self, project_id: UUID, key: str) -> None:
        """Remove one metadata entry, if present (a no-op otherwise)."""
        existing = await self._metadata.get_by_key(project_id, key)
        if existing is not None:
            await self._metadata.delete(existing.id)


__all__ = ["ProjectMetadataService"]
