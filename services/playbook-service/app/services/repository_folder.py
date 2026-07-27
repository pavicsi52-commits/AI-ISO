"""Playbook repository folders, per docs/041 "REPOSITORY" "Support":
Folder Organization, Shared Repository, Organization Repository,
Project Repository.
"""

from __future__ import annotations

from uuid import UUID

from app.models.enums import RepositoryType, RepositoryVisibility
from app.models.playbook_repository import PlaybookRepositoryFolder
from app.repositories.playbook_repository import PlaybookRepositoryFolderRepository


class PlaybookRepositoryFolderService:
    """Creates, reads, and deletes playbook repository folders."""

    def __init__(self, folders: PlaybookRepositoryFolderRepository) -> None:
        self._folders = folders

    async def get_by_id(self, repository_id: UUID) -> PlaybookRepositoryFolder:
        """Return the repository folder identified by *repository_id*.

        Raises:
            NotFoundError: If no such repository folder exists.
        """
        return await self._folders.require_by_id(repository_id)

    async def list_for_org(self, organization_id: UUID) -> list[PlaybookRepositoryFolder]:
        """Every repository folder belonging to *organization_id*."""
        return await self._folders.list_for_org(organization_id)

    async def create(
        self,
        *,
        organization_id: UUID,
        name: str,
        description: str | None,
        repository_type: RepositoryType,
        visibility: RepositoryVisibility,
    ) -> PlaybookRepositoryFolder:
        """Define a new playbook repository folder ("Folder Organization")."""
        return await self._folders.create(
            PlaybookRepositoryFolder(
                organization_id=organization_id,
                name=name,
                description=description,
                repository_type=repository_type,
                visibility=visibility,
            )
        )

    async def delete(self, repository_id: UUID) -> None:
        """Soft-delete a playbook repository folder."""
        await self._folders.delete(repository_id)


__all__ = ["PlaybookRepositoryFolderService"]
