"""The webhook transformation repository."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transformation import WebhookTransformation


class WebhookTransformationRepository(BaseRepository[WebhookTransformation]):
    """Payload/header transformation rules attached to an endpoint."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, WebhookTransformation, tenant_scope=tenant_scope)

    async def require_in_org(
        self, organization_id: UUID, transformation_id: UUID
    ) -> WebhookTransformation:
        """One transformation rule by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(WebhookTransformation.organization_id == organization_id)
            .where(WebhookTransformation.id == transformation_id)
        )
        result = await self._session.execute(stmt)
        found: WebhookTransformation | None = result.scalars().first()
        if found is None:
            raise NotFoundError(
                f"No transformation rule with id {transformation_id} in this organization."
            )
        return found

    async def list_for_endpoint(self, endpoint_id: UUID) -> list[WebhookTransformation]:
        """Every enabled transformation rule attached to one endpoint, in priority order."""
        stmt = (
            self._base_select()
            .where(WebhookTransformation.endpoint_id == endpoint_id)
            .where(WebhookTransformation.enabled.is_(True))
            .order_by(WebhookTransformation.priority)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["WebhookTransformationRepository"]
