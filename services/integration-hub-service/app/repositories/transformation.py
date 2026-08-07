"""``connector_transformations`` repository."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transformation import ConnectorTransformation


class ConnectorTransformationRepository(BaseRepository[ConnectorTransformation]):
    """Payload-shaping rules attached to a connector."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ConnectorTransformation, tenant_scope=tenant_scope)

    async def require_in_org(
        self, organization_id: UUID, transformation_id: UUID
    ) -> ConnectorTransformation:
        """One transformation by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(ConnectorTransformation.organization_id == organization_id)
            .where(ConnectorTransformation.id == transformation_id)
        )
        result = await self._session.execute(stmt)
        found: ConnectorTransformation | None = result.scalars().first()
        if found is None:
            raise NotFoundError(
                f"No transformation with id {transformation_id} in this organization."
            )
        return found

    async def list_for_connector(
        self, connector_id: UUID, *, enabled: bool | None = None
    ) -> list[ConnectorTransformation]:
        """Every transformation attached to one connector, in priority order."""
        stmt = self._base_select().where(ConnectorTransformation.connector_id == connector_id)
        if enabled is not None:
            stmt = stmt.where(ConnectorTransformation.enabled.is_(enabled))
        stmt = stmt.order_by(ConnectorTransformation.priority)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ConnectorTransformationRepository"]
