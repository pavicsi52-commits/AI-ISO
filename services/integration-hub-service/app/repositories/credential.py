"""``connector_credentials`` and ``connector_connections`` repositories."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.credential import ConnectorConnection, ConnectorCredential
from app.models.enums import CredentialStatus


class ConnectorCredentialRepository(BaseRepository[ConnectorCredential]):
    """One connector's own assigned credential(s)."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ConnectorCredential, tenant_scope=tenant_scope)

    async def require_in_org(
        self, organization_id: UUID, credential_id: UUID
    ) -> ConnectorCredential:
        """One credential by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(ConnectorCredential.organization_id == organization_id)
            .where(ConnectorCredential.id == credential_id)
        )
        result = await self._session.execute(stmt)
        found: ConnectorCredential | None = result.scalars().first()
        if found is None:
            raise NotFoundError(
                f"No connector credential with id {credential_id} in this organization."
            )
        return found

    async def list_for_connector(self, connector_id: UUID) -> list[ConnectorCredential]:
        """Every credential assigned to one connector, newest first."""
        stmt = (
            self._base_select()
            .where(ConnectorCredential.connector_id == connector_id)
            .order_by(ConnectorCredential.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_active_for_connector(self, connector_id: UUID) -> ConnectorCredential | None:
        """The one credential a connector actually authenticates with right now, if any."""
        stmt = (
            self._base_select()
            .where(ConnectorCredential.connector_id == connector_id)
            .where(ConnectorCredential.status == str(CredentialStatus.ACTIVE))
            .order_by(ConnectorCredential.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_expiring_before(
        self, cutoff: datetime, *, limit: int = 500
    ) -> list[ConnectorCredential]:
        """Active credentials past *cutoff*'s own ``expires_at`` -- for the expiry sweep."""
        stmt = (
            self._base_select()
            .where(ConnectorCredential.status == str(CredentialStatus.ACTIVE))
            .where(ConnectorCredential.expires_at.is_not(None))
            .where(ConnectorCredential.expires_at <= cutoff)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class ConnectorConnectionRepository(BaseRepository[ConnectorConnection]):
    """Discrete connector test/validate/connect attempts."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ConnectorConnection, tenant_scope=tenant_scope)

    async def list_for_connector(
        self, connector_id: UUID, *, limit: int = 50
    ) -> list[ConnectorConnection]:
        """Recent connection attempts for one connector, newest first."""
        stmt = (
            self._base_select()
            .where(ConnectorConnection.connector_id == connector_id)
            .order_by(ConnectorConnection.tested_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ConnectorConnectionRepository", "ConnectorCredentialRepository"]
