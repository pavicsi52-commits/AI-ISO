"""Report archiving ("ARCHIVE").

Version history, retention policies, immutable storage, search,
restore, and download.

The archive keeps its **own copy** of the bytes and checksum rather
than referencing the live export row. Regenerating or deleting a
report therefore cannot retroactively change what was archived, which
is the only thing that makes an archive worth having for compliance.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from shared_core.exceptions.conflict import ConflictError
from shared_core.logging.logger import get_logger

from app.archive.retention import ensure_purgeable, retention_deadline, verify_integrity
from app.events.report_events import SOURCE_SERVICE, ReportArchivedEvent
from app.models.enums import ArchiveStatus, ExportFormat
from app.models.report_archive import ReportArchive
from app.models.report_export import ReportExport
from app.repositories.report_archive import ReportArchiveRepository
from app.repositories.report_export import ReportExportRepository
from app.types import EventPublisher

logger = get_logger("app.services.archive")


class ReportArchiveService:
    """Archives, searches, restores, and purges report artifacts."""

    def __init__(
        self,
        archives: ReportArchiveRepository,
        exports: ReportExportRepository,
        *,
        publish_event: EventPublisher,
        retention_days: int,
    ) -> None:
        self._archives = archives
        self._exports = exports
        self._publish_event = publish_event
        self._retention_days = retention_days

    async def archive_export(
        self,
        export_record: ReportExport,
        *,
        title: str,
        job_id: UUID | None = None,
        retention_days: int | None = None,
    ) -> ReportArchive:
        """Archive one rendered artifact.

        The version number comes from ``MAX(version) + 1`` in SQL, so a
        purged intermediate version can never cause a collision.
        Retention is computed and stored now, not derived later.
        """
        archived_at = datetime.now(UTC)
        days = retention_days if retention_days is not None else self._retention_days
        next_version = await self._archives.next_version(export_record.organization_id, title)

        archive = await self._archives.create(
            ReportArchive(
                organization_id=export_record.organization_id,
                project_id=export_record.project_id,
                execution_id=export_record.execution_id,
                job_id=job_id,
                title=title,
                export_format=(
                    export_record.export_format
                    if isinstance(export_record.export_format, ExportFormat)
                    else ExportFormat(export_record.export_format)
                ),
                filename=export_record.filename,
                content_type=export_record.content_type,
                size_bytes=export_record.size_bytes,
                checksum_sha256=export_record.checksum_sha256,
                archive_version=next_version,
                status=ArchiveStatus.ACTIVE,
                archived_at=archived_at,
                retention_until=retention_deadline(archived_at=archived_at, retention_days=days),
                content=export_record.content,
            )
        )
        await self._publish_event(
            ReportArchivedEvent(
                source_service=SOURCE_SERVICE,
                payload={
                    "archive_id": str(archive.id),
                    "title": title,
                    "archive_version": next_version,
                    "retention_until": (
                        archive.retention_until.isoformat() if archive.retention_until else None
                    ),
                },
            )
        )
        return archive

    async def get_by_id(self, archive_id: UUID) -> ReportArchive:
        """Return one archived artifact.

        Raises:
            NotFoundError: If no such archive exists.
        """
        return await self._archives.require_by_id(archive_id)

    async def list_for_org(
        self,
        organization_id: UUID,
        *,
        status: ArchiveStatus | None = None,
        limit: int = 200,
    ) -> list[ReportArchive]:
        """Archived artifacts for an organization."""
        return await self._archives.list_for_org(organization_id, status=status, limit=limit)

    async def search(
        self, organization_id: UUID, term: str, *, limit: int = 100
    ) -> list[ReportArchive]:
        """Search archived report titles."""
        return await self._archives.search_titles(organization_id, term, limit=limit)

    async def list_versions(self, organization_id: UUID, title: str) -> list[ReportArchive]:
        """Every archived version of one report title."""
        return await self._archives.list_versions(organization_id, title)

    async def download(self, archive_id: UUID) -> ReportArchive:
        """Fetch an archived artifact, verifying its integrity first.

        Raises:
            NotFoundError: If no such archive exists.
            ConflictError: If it has been purged, or the stored bytes no
                longer match the stored checksum. Serving content that
                fails its own checksum would silently hand an auditor a
                corrupted document.
        """
        archive = await self._archives.require_by_id(archive_id)
        status = (
            archive.status
            if isinstance(archive.status, ArchiveStatus)
            else ArchiveStatus(archive.status)
        )
        if status is ArchiveStatus.PURGED:
            raise ConflictError(f"Archive {archive_id!r} has been purged.")
        if not verify_integrity(archive):
            logger.error(
                "Archive integrity check failed.",
                extra={"extra_fields": {"archive_id": str(archive_id)}},
            )
            raise ConflictError(
                f"Archive {archive_id!r} failed its integrity check and will not be served."
            )
        return archive

    async def restore(self, archive_id: UUID) -> ReportExport:
        """Restore an archived artifact back into live exports.

        A *new* export row is created rather than resurrecting the old
        one: the original may have been superseded, and an archive
        restore must not silently overwrite current state.

        Raises:
            NotFoundError: If no such archive exists.
            ConflictError: If it is purged or fails its integrity check.
        """
        archive = await self.download(archive_id)
        if archive.execution_id is None:
            raise ConflictError(f"Archive {archive_id!r} has no execution to restore against.")
        restored = await self._exports.create(
            ReportExport(
                organization_id=archive.organization_id,
                project_id=archive.project_id,
                execution_id=archive.execution_id,
                export_format=archive.export_format,
                filename=archive.filename,
                content_type=archive.content_type,
                size_bytes=archive.size_bytes,
                checksum_sha256=archive.checksum_sha256,
                content=archive.content,
            )
        )
        archive.status = ArchiveStatus.RESTORED
        await self._archives.update(archive)
        return restored

    async def purge(self, archive_id: UUID, *, reason: str | None = None) -> ReportArchive:
        """Purge an archived artifact once its retention has elapsed.

        The row is retained with its metadata and marked ``PURGED``;
        only the bytes are dropped. Deleting the row entirely would
        erase the evidence that the artifact ever existed, which defeats
        the audit trail the archive exists for.

        Raises:
            NotFoundError: If no such archive exists.
            ConflictError: If it is still within its retention window.
        """
        archive = await self._archives.require_by_id(archive_id)
        ensure_purgeable(archive)
        archive.status = ArchiveStatus.PURGED
        archive.purge_reason = reason or "Retention period elapsed."
        archive.content = b""
        archive.size_bytes = 0
        return await self._archives.update(archive)

    async def purge_expired(self, *, limit: int = 200) -> int:
        """Purge every archive past its retention; returns how many.

        Sequential, not gathered: each purge writes a row, and an
        ``AsyncSession`` is not safe for concurrent use.
        """
        expired = await self._archives.list_expired(datetime.now(UTC), limit=limit)
        purged = 0
        for archive in expired:
            await self.purge(archive.id, reason="Retention period elapsed.")
            purged += 1
        return purged


__all__ = ["ReportArchiveService"]
