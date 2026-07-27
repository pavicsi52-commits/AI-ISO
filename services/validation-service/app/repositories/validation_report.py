"""Repository for :class:`app.models.validation_report.ValidationReport`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ValidationReportType
from app.models.validation_report import ValidationReport


class ValidationReportRepository(BaseRepository[ValidationReport]):
    """CRUD plus lookup for :class:`ValidationReport`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ValidationReport, tenant_scope=tenant_scope)

    async def list_for_org(
        self, organization_id: UUID, *, report_type: ValidationReportType | None = None
    ) -> list[ValidationReport]:
        """Every report generated for *organization_id*, optionally filtered by type."""
        stmt = self._base_select().where(ValidationReport.organization_id == organization_id)
        if report_type is not None:
            stmt = stmt.where(ValidationReport.report_type == report_type)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ValidationReportRepository"]
