"""Repository for :class:`app.models.dashboard_share.DashboardShare`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dashboard_share import DashboardShare


class DashboardShareRepository(BaseRepository[DashboardShare]):
    """CRUD plus lookups for :class:`DashboardShare`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, DashboardShare, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[DashboardShare]:
        """Every share belonging to *organization_id*."""
        stmt = self._base_select().where(DashboardShare.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_dashboard(
        self, dashboard_id: UUID, *, active_only: bool = False
    ) -> list[DashboardShare]:
        """Shares of one dashboard, revoked ones included by default.

        Revoked shares are visible because "who *used* to have access?"
        is a question an auditor asks; ``active_only`` is for the
        access-control path.
        """
        stmt = self._base_select().where(DashboardShare.dashboard_id == dashboard_id)
        if active_only:
            stmt = stmt.where(DashboardShare.is_revoked.is_(False))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_user(self, organization_id: UUID, user_id: UUID) -> list[DashboardShare]:
        """Active shares directed at one user."""
        stmt = self._base_select().where(
            DashboardShare.organization_id == organization_id,
            DashboardShare.shared_with_user_id == user_id,
            DashboardShare.is_revoked.is_(False),
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_token(self, share_token: str) -> DashboardShare | None:
        """Resolve a read-only link by its token.

        Deliberately **not** scoped to an organization: the token is the
        credential, presented by someone with no session. Revocation and
        expiry are enforced by the caller, which is what makes the link
        genuinely time-limited rather than merely labelled so.
        """
        stmt = self._base_select().where(DashboardShare.share_token == share_token)
        result = await self._session.execute(stmt)
        return result.scalars().first()


__all__ = ["DashboardShareRepository"]
