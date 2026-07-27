"""Repository for :class:`app.models.validation_rule.ValidationRule`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.validation_rule import ValidationRule


class ValidationRuleRepository(BaseRepository[ValidationRule]):
    """CRUD plus lookup for :class:`ValidationRule`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ValidationRule, tenant_scope=tenant_scope)

    async def list_for_check(self, check_id: UUID) -> list[ValidationRule]:
        """Every active rule for *check_id*, evaluation order (lowest priority first)."""
        stmt = (
            self._base_select()
            .where(ValidationRule.check_id == check_id, ValidationRule.is_active.is_(True))
            .order_by(ValidationRule.priority.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ValidationRuleRepository"]
