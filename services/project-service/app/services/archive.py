"""Project archive/restore snapshot tracking. Per docs/034 "PROJECT
LIFECYCLE": Archive, Restore. Backs
``app/services/project.py::ProjectService.archive()``/``restore()``,
which own the actual status transition on :class:`~app.models.project
.Project` itself -- this service only records the event and its
snapshot.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.exceptions.not_found import NotFoundError

from app.models.project_archive import ProjectArchive
from app.repositories.project_archive import ProjectArchiveRepository


class ProjectArchiveService:
    """Records archive events and their eventual restore."""

    def __init__(self, archives: ProjectArchiveRepository) -> None:
        self._archives = archives

    async def list_for_project(self, project_id: UUID) -> list[ProjectArchive]:
        """Every archive event for *project_id*, newest first."""
        return await self._archives.list_for_project(project_id)

    async def record_archive(
        self,
        project_id: UUID,
        *,
        organization_id: UUID,
        archived_by: UUID | None,
        reason: str | None,
        snapshot: dict[str, Any],
    ) -> ProjectArchive:
        """Record a new archive event ("Archive")."""
        return await self._archives.create(
            ProjectArchive(
                project_id=project_id,
                organization_id=organization_id,
                archived_by=archived_by,
                reason=reason,
                archived_at=datetime.now(UTC),
                snapshot=snapshot,
            )
        )

    async def record_restore(self, project_id: UUID, *, restored_by: UUID | None) -> ProjectArchive:
        """Record the restore of *project_id*'s most recent archive event
        ("Restore").

        Raises:
            NotFoundError: If *project_id* has no unrestored archive event.
        """
        archive = await self._archives.get_latest_unrestored(project_id)
        if archive is None:
            raise NotFoundError("This project has no unrestored archive event.")
        archive.restored_by = restored_by
        archive.restored_at = datetime.now(UTC)
        return archive


__all__ = ["ProjectArchiveService"]
