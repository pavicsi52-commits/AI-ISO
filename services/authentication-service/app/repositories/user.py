"""Repository for :class:`app.models.user.User`."""

from __future__ import annotations

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UserRepository(BaseRepository[User]):
    """CRUD plus email lookup for :class:`User`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, User, tenant_scope=tenant_scope)

    async def get_by_email(self, email: str, *, include_deleted: bool = False) -> User | None:
        """Return the user with *email* (case-sensitive; callers normalize casing), or ``None``."""
        stmt = self._base_select(include_deleted=include_deleted).where(User.email == email)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["UserRepository"]
