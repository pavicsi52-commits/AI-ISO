"""The webhook signature (signing secret) repository."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import SecretStatus
from app.models.signature import WebhookSignature


class WebhookSignatureRepository(BaseRepository[WebhookSignature]):
    """An endpoint's own signing secrets, one row per rotation version."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, WebhookSignature, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, signature_id: UUID) -> WebhookSignature:
        """One signing-secret row by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(WebhookSignature.organization_id == organization_id)
            .where(WebhookSignature.id == signature_id)
        )
        result = await self._session.execute(stmt)
        found: WebhookSignature | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No signing secret with id {signature_id} in this organization.")
        return found

    async def list_usable_for_endpoint(self, endpoint_id: UUID) -> list[WebhookSignature]:
        """Every ``ACTIVE``/``ROTATING`` secret for one endpoint, newest version first.

        Both statuses are usable for *verifying* an inbound signature --
        only ``ACTIVE`` is ever used to *sign* a new outbound delivery.
        """
        stmt = (
            self._base_select()
            .where(WebhookSignature.endpoint_id == endpoint_id)
            .where(WebhookSignature.status.in_([str(SecretStatus.ACTIVE), str(SecretStatus.ROTATING)]))
            .order_by(WebhookSignature.version.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_active_for_endpoint(self, endpoint_id: UUID) -> WebhookSignature | None:
        """The one ``ACTIVE`` secret for an endpoint, if any -- used to sign new deliveries."""
        stmt = (
            self._base_select()
            .where(WebhookSignature.endpoint_id == endpoint_id)
            .where(WebhookSignature.status == str(SecretStatus.ACTIVE))
            .order_by(WebhookSignature.version.desc())
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def get_latest_version(self, endpoint_id: UUID) -> int:
        """The highest existing ``version`` for an endpoint's own secrets, or ``0`` if none."""
        rows = await self.list_usable_for_endpoint(endpoint_id)
        return max((row.version for row in rows), default=0)


__all__ = ["WebhookSignatureRepository"]
