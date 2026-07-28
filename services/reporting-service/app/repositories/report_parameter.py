"""Repository for :class:`app.models.report_parameter.ReportParameter`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_parameter import ReportParameter


class ReportParameterRepository(BaseRepository[ReportParameter]):
    """CRUD plus lookups for :class:`ReportParameter`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ReportParameter, tenant_scope=tenant_scope)

    async def list_for_template(self, template_id: UUID) -> list[ReportParameter]:
        """Every parameter a template declares, in display order."""
        stmt = (
            self._base_select()
            .where(ReportParameter.template_id == template_id)
            .order_by(ReportParameter.display_order, ReportParameter.key)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def delete_for_template(self, template_id: UUID) -> int:
        """Remove every parameter of a template; returns how many.

        Used when a template's parameter set is replaced wholesale, so
        a removed parameter cannot linger and be silently required.
        """
        existing = await self.list_for_template(template_id)
        for parameter in existing:
            await self.purge(parameter.id)
        return len(existing)


__all__ = ["ReportParameterRepository"]
