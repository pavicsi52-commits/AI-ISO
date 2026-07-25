"""Repository for :class:`app.models.member.OrganizationMember`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.member import OrganizationMember


class OrganizationMemberRepository(BaseRepository[OrganizationMember]):
    """CRUD plus lookup for :class:`OrganizationMember`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, OrganizationMember, tenant_scope=tenant_scope)

    async def get(self, organization_id: UUID, user_id: UUID) -> OrganizationMember | None:
        """Return *user_id*'s membership in *organization_id*, or ``None``."""
        stmt = self._base_select().where(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.user_id == user_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_org(self, organization_id: UUID) -> list[OrganizationMember]:
        """Every member of *organization_id*."""
        stmt = self._base_select().where(OrganizationMember.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_user(self, user_id: UUID) -> list[OrganizationMember]:
        """Every organization *user_id* belongs to."""
        stmt = self._base_select().where(OrganizationMember.user_id == user_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_for_org(self, organization_id: UUID) -> int:
        """The number of members in *organization_id* ("Enforce quotas")."""
        return await self.count(organization_id=organization_id)


__all__ = ["OrganizationMemberRepository"]
