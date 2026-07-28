"""Repository for :class:`app.models.report_distribution.ReportDistribution`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import DistributionStatus
from app.models.report_distribution import ReportDistribution


class ReportDistributionRepository(BaseRepository[ReportDistribution]):
    """CRUD plus lookups for :class:`ReportDistribution`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ReportDistribution, tenant_scope=tenant_scope)

    async def list_for_export(self, export_id: UUID) -> list[ReportDistribution]:
        """Every delivery attempt for one artifact, including failures."""
        stmt = (
            self._base_select()
            .where(ReportDistribution.export_id == export_id)
            .order_by(ReportDistribution.created_at)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_org(
        self,
        organization_id: UUID,
        *,
        status: DistributionStatus | None = None,
        limit: int = 200,
    ) -> list[ReportDistribution]:
        """Delivery attempts for *organization_id*, most recent first."""
        stmt = self._base_select().where(ReportDistribution.organization_id == organization_id)
        if status is not None:
            stmt = stmt.where(ReportDistribution.status == status)
        stmt = stmt.order_by(desc(ReportDistribution.created_at)).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_share_token(self, share_token: str) -> ReportDistribution | None:
        """Resolve a shared link by its token.

        Deliberately *not* scoped to an organization: the token is the
        credential, presented by a recipient who has no session. Expiry
        is enforced by the caller, which is what makes the link
        genuinely time-limited rather than merely labelled so.
        """
        stmt = self._base_select().where(ReportDistribution.share_token == share_token)
        result = await self._session.execute(stmt)
        return result.scalars().first()


__all__ = ["ReportDistributionRepository"]
