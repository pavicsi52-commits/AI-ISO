"""Repository for :class:`app.models.configuration_compliance.ConfigurationCompliance`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.configuration_compliance import ConfigurationCompliance
from app.models.enums import ComplianceEvalType


class ConfigurationComplianceRepository(BaseRepository[ConfigurationCompliance]):
    """CRUD plus lookup for :class:`ConfigurationCompliance`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ConfigurationCompliance, tenant_scope=tenant_scope)

    async def list_for_profile(
        self, profile_id: UUID, *, eval_type: ComplianceEvalType | None = None
    ) -> list[ConfigurationCompliance]:
        """Every compliance evaluation for *profile_id*, newest first,
        optionally narrowed to a single *eval_type*.
        """
        stmt = self._base_select().where(ConfigurationCompliance.profile_id == profile_id)
        if eval_type is not None:
            stmt = stmt.where(ConfigurationCompliance.eval_type == eval_type)
        stmt = stmt.order_by(desc(ConfigurationCompliance.checked_at))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ConfigurationComplianceRepository"]
