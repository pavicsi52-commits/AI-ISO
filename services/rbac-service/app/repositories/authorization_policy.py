"""Repository for :class:`app.models.authorization_policy.AuthorizationPolicy`."""

from __future__ import annotations

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.authorization_policy import AuthorizationPolicy
from app.models.enums import PolicyStatus


class AuthorizationPolicyRepository(BaseRepository[AuthorizationPolicy]):
    """CRUD plus lookup for :class:`AuthorizationPolicy`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AuthorizationPolicy, tenant_scope=tenant_scope)

    async def get_by_code(self, code: str) -> AuthorizationPolicy | None:
        """Return the policy identified by *code*, or ``None``."""
        stmt = self._base_select().where(AuthorizationPolicy.code == code)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_active(self) -> list[AuthorizationPolicy]:
        """Every active policy, highest priority first ("Efficient policy evaluation")."""
        stmt = (
            self._base_select()
            .where(AuthorizationPolicy.status == PolicyStatus.ACTIVE)
            .order_by(desc(AuthorizationPolicy.priority))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AuthorizationPolicyRepository"]
