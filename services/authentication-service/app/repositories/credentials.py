"""Repository for :class:`app.models.credentials.UserCredential`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.credentials import UserCredential
from app.models.enums import CredentialType


class UserCredentialRepository(BaseRepository[UserCredential]):
    """CRUD plus per-user credential lookup for :class:`UserCredential`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, UserCredential, tenant_scope=tenant_scope)

    async def get_for_user(
        self, user_id: UUID, *, credential_type: CredentialType = CredentialType.PASSWORD
    ) -> UserCredential | None:
        """Return *user_id*'s credential of *credential_type*, or ``None``."""
        stmt = self._base_select().where(
            UserCredential.user_id == user_id,
            UserCredential.credential_type == credential_type,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["UserCredentialRepository"]
