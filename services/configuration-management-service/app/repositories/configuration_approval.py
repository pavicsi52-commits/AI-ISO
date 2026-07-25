"""Repository for :class:`app.models.configuration_approval.ConfigurationApproval`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.configuration_approval import ConfigurationApproval
from app.models.enums import ApprovalStatus


class ConfigurationApprovalRepository(BaseRepository[ConfigurationApproval]):
    """CRUD plus lookup for :class:`ConfigurationApproval`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ConfigurationApproval, tenant_scope=tenant_scope)

    async def list_for_profile(self, profile_id: UUID) -> list[ConfigurationApproval]:
        """Every approval step recorded for *profile_id* ("Approval History")."""
        stmt = self._base_select().where(ConfigurationApproval.profile_id == profile_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_version(self, version_id: UUID) -> list[ConfigurationApproval]:
        """Every approval step recorded for *version_id*."""
        stmt = self._base_select().where(ConfigurationApproval.version_id == version_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_rollback(self, rollback_id: UUID) -> list[ConfigurationApproval]:
        """Every approval step recorded for *rollback_id*."""
        stmt = self._base_select().where(ConfigurationApproval.rollback_id == rollback_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_pending_for_org(self, organization_id: UUID) -> list[ConfigurationApproval]:
        """Every still-pending approval for *organization_id*."""
        stmt = self._base_select().where(
            ConfigurationApproval.organization_id == organization_id,
            ConfigurationApproval.status == ApprovalStatus.PENDING,
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ConfigurationApprovalRepository"]
