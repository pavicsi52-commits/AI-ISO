"""The change conflict repository."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conflict import ChangeConflict
from app.models.enums import ConflictStatus


class ChangeConflictRepository(BaseRepository[ChangeConflict]):
    """Detected scheduling conflicts between changes."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ChangeConflict, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, conflict_id: UUID) -> ChangeConflict:
        """One conflict by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(ChangeConflict.organization_id == organization_id)
            .where(ChangeConflict.id == conflict_id)
        )
        result = await self._session.execute(stmt)
        found: ChangeConflict | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No conflict with id {conflict_id} in this organization.")
        return found

    async def list_for_change(
        self, organization_id: UUID, change_id: UUID, *, limit: int = 200
    ) -> list[ChangeConflict]:
        """Every conflict naming this change on either side."""
        stmt = (
            self._base_select()
            .where(ChangeConflict.organization_id == organization_id)
            .where(
                or_(
                    ChangeConflict.change_id == change_id,
                    ChangeConflict.conflicting_change_id == change_id,
                )
            )
            .order_by(ChangeConflict.detected_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_active(self, organization_id: UUID, *, limit: int = 500) -> list[ChangeConflict]:
        """Every conflict still open -- detected or acknowledged, not yet resolved."""
        stmt = (
            self._base_select()
            .where(ChangeConflict.organization_id == organization_id)
            .where(
                ChangeConflict.status.in_(
                    [str(ConflictStatus.DETECTED), str(ConflictStatus.ACKNOWLEDGED)]
                )
            )
            .order_by(ChangeConflict.detected_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ChangeConflictRepository"]
