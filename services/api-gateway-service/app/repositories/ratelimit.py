"""The API rate limit policy repository."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import RateLimitScope
from app.models.ratelimit import ApiRateLimitPolicy


class ApiRateLimitPolicyRepository(BaseRepository[ApiRateLimitPolicy]):
    """Configured rate-limit policies."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ApiRateLimitPolicy, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, policy_id: UUID) -> ApiRateLimitPolicy:
        """One policy by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(ApiRateLimitPolicy.organization_id == organization_id)
            .where(ApiRateLimitPolicy.id == policy_id)
        )
        result = await self._session.execute(stmt)
        found: ApiRateLimitPolicy | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No rate limit policy with id {policy_id} in this organization.")
        return found

    async def list_for_org(self, organization_id: UUID) -> list[ApiRateLimitPolicy]:
        """Every rate-limit policy configured in this organization."""
        stmt = self._base_select().where(ApiRateLimitPolicy.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def find(
        self, organization_id: UUID, scope: RateLimitScope, scope_reference: str | None
    ) -> ApiRateLimitPolicy | None:
        """The policy matching this exact scope/reference, if any."""
        stmt = (
            self._base_select()
            .where(ApiRateLimitPolicy.organization_id == organization_id)
            .where(ApiRateLimitPolicy.scope == str(scope))
            .where(ApiRateLimitPolicy.scope_reference == scope_reference)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()


__all__ = ["ApiRateLimitPolicyRepository"]
