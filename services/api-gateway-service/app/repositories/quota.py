"""The API quota policy repository."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import QuotaKind, QuotaScope
from app.models.quota import ApiQuotaPolicy


class ApiQuotaPolicyRepository(BaseRepository[ApiQuotaPolicy]):
    """Configured quotas and their own live usage."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ApiQuotaPolicy, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, quota_id: UUID) -> ApiQuotaPolicy:
        """One quota by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(ApiQuotaPolicy.organization_id == organization_id)
            .where(ApiQuotaPolicy.id == quota_id)
        )
        result = await self._session.execute(stmt)
        found: ApiQuotaPolicy | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No quota with id {quota_id} in this organization.")
        return found

    async def list_for_org(self, organization_id: UUID) -> list[ApiQuotaPolicy]:
        """Every quota configured in this organization."""
        stmt = self._base_select().where(ApiQuotaPolicy.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def find(
        self,
        organization_id: UUID,
        scope: QuotaScope,
        scope_reference: str | None,
        kind: QuotaKind,
    ) -> ApiQuotaPolicy | None:
        """The quota matching this exact scope/reference/kind, if any."""
        stmt = (
            self._base_select()
            .where(ApiQuotaPolicy.organization_id == organization_id)
            .where(ApiQuotaPolicy.scope == str(scope))
            .where(ApiQuotaPolicy.scope_reference == scope_reference)
            .where(ApiQuotaPolicy.kind == str(kind))
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_due_for_reset(self, *, now: datetime, limit: int = 500) -> list[ApiQuotaPolicy]:
        """Every quota whose tracked period has already ended, across every organization.

        Unscoped by organization -- the quota-reset sweep is a single
        leader-elected worker walking every organization's due resets
        in one tick.
        """
        stmt = self._base_select().where(ApiQuotaPolicy.period_resets_at <= now).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ApiQuotaPolicyRepository"]
