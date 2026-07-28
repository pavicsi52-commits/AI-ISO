"""Repository for :class:`app.models.report_archive.ReportArchive`."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ArchiveStatus
from app.models.report_archive import ReportArchive


class ReportArchiveRepository(BaseRepository[ReportArchive]):
    """CRUD plus lookups for :class:`ReportArchive`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ReportArchive, tenant_scope=tenant_scope)

    async def list_for_org(
        self,
        organization_id: UUID,
        *,
        status: ArchiveStatus | None = None,
        limit: int = 200,
    ) -> list[ReportArchive]:
        """Archived artifacts for *organization_id*, newest first."""
        stmt = self._base_select().where(ReportArchive.organization_id == organization_id)
        if status is not None:
            stmt = stmt.where(ReportArchive.status == status)
        stmt = stmt.order_by(desc(ReportArchive.archived_at)).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def search_titles(
        self, organization_id: UUID, term: str, *, limit: int = 100
    ) -> list[ReportArchive]:
        """Case-insensitive title search ("ARCHIVE": Search).

        Deliberately **not** named ``search``: :class:`BaseRepository`
        already defines a generic multi-field ``search`` with a
        different signature, and shadowing it would break any caller
        that reached for the inherited one.

        Matching is pushed into SQL. Loading the whole archive to filter
        in Python would defeat the point of an archive that grows
        without bound.
        """
        stmt = (
            self._base_select()
            .where(
                ReportArchive.organization_id == organization_id,
                ReportArchive.title.ilike(f"%{term}%"),
            )
            .order_by(desc(ReportArchive.archived_at))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_versions(self, organization_id: UUID, title: str) -> list[ReportArchive]:
        """Every archived version of one report title, oldest first."""
        stmt = (
            self._base_select()
            .where(
                ReportArchive.organization_id == organization_id,
                ReportArchive.title == title,
            )
            .order_by(ReportArchive.archive_version)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def next_version(self, organization_id: UUID, title: str) -> int:
        """The next version number for a title, computed in SQL.

        Using ``MAX(version) + 1`` rather than ``len(rows) + 1`` so a
        purged intermediate version can never cause a collision with an
        existing row.
        """
        stmt = (
            self._base_select()
            .with_only_columns(func.max(ReportArchive.archive_version))
            .where(
                ReportArchive.organization_id == organization_id,
                ReportArchive.title == title,
            )
        )
        result = await self._session.execute(stmt)
        highest = result.scalar_one_or_none()
        return int(highest or 0) + 1

    async def list_expired(self, moment: datetime, *, limit: int = 200) -> list[ReportArchive]:
        """Active archives whose retention has elapsed."""
        stmt = (
            self._base_select()
            .where(
                ReportArchive.status == ArchiveStatus.ACTIVE,
                ReportArchive.retention_until.is_not(None),
                ReportArchive.retention_until <= moment,
            )
            .order_by(ReportArchive.retention_until)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ReportArchiveRepository"]
