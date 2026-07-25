"""Repositories for :class:`app.models.token.RefreshToken`/:class:`AccessToken`."""

from __future__ import annotations

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.token import AccessToken, RefreshToken


class RefreshTokenRepository(BaseRepository[RefreshToken]):
    """CRUD plus ``jti`` lookup for :class:`RefreshToken`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, RefreshToken, tenant_scope=tenant_scope)

    async def get_by_jti(self, jti: str) -> RefreshToken | None:
        """Return the refresh token tracked under *jti*, or ``None``."""
        stmt = self._base_select().where(RefreshToken.jti == jti)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


class AccessTokenRepository(BaseRepository[AccessToken]):
    """CRUD plus ``jti`` lookup for :class:`AccessToken`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AccessToken, tenant_scope=tenant_scope)

    async def get_by_jti(self, jti: str) -> AccessToken | None:
        """Return the access token tracked under *jti*, or ``None``."""
        stmt = self._base_select().where(AccessToken.jti == jti)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["AccessTokenRepository", "RefreshTokenRepository"]
