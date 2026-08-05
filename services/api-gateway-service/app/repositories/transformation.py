"""The API transformation rule repository."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transformation import ApiTransformationRule


class ApiTransformationRuleRepository(BaseRepository[ApiTransformationRule]):
    """Configured request/response transformation rules."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ApiTransformationRule, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, rule_id: UUID) -> ApiTransformationRule:
        """One rule by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(ApiTransformationRule.organization_id == organization_id)
            .where(ApiTransformationRule.id == rule_id)
        )
        result = await self._session.execute(stmt)
        found: ApiTransformationRule | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No transformation rule with id {rule_id} in this organization.")
        return found

    async def list_for_route(
        self, organization_id: UUID, route_id: UUID | None
    ) -> list[ApiTransformationRule]:
        """Every enabled rule that applies to *route_id* -- global rules (``route_id is None``)
        plus any rule scoped specifically to this route, ordered by priority."""
        stmt = (
            self._base_select()
            .where(ApiTransformationRule.organization_id == organization_id)
            .where(ApiTransformationRule.enabled.is_(True))
            .where(
                (ApiTransformationRule.route_id.is_(None))
                | (ApiTransformationRule.route_id == route_id)
            )
            .order_by(ApiTransformationRule.priority)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ApiTransformationRuleRepository"]
