"""The risk assessment repository."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.risk import ChangeRiskAssessment


class ChangeRiskAssessmentRepository(BaseRepository[ChangeRiskAssessment]):
    """Risk assessments recorded against changes."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ChangeRiskAssessment, tenant_scope=tenant_scope)

    async def list_for_change(
        self, organization_id: UUID, change_id: UUID
    ) -> list[ChangeRiskAssessment]:
        """Every assessment for one change, in the order they were recorded."""
        stmt = (
            self._base_select()
            .where(ChangeRiskAssessment.organization_id == organization_id)
            .where(ChangeRiskAssessment.change_id == change_id)
            .order_by(ChangeRiskAssessment.assessed_at)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def latest_for_change(
        self, organization_id: UUID, change_id: UUID
    ) -> ChangeRiskAssessment | None:
        """The most recent assessment for one change, if any."""
        stmt = (
            self._base_select()
            .where(ChangeRiskAssessment.organization_id == organization_id)
            .where(ChangeRiskAssessment.change_id == change_id)
            .order_by(ChangeRiskAssessment.assessed_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()


__all__ = ["ChangeRiskAssessmentRepository"]
