"""Repository for :class:`app.models.alert_acknowledgement.AlertAcknowledgement`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert_acknowledgement import AlertAcknowledgement


class AlertAcknowledgementRepository(BaseRepository[AlertAcknowledgement]):
    """CRUD plus lookup for :class:`AlertAcknowledgement`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AlertAcknowledgement, tenant_scope=tenant_scope)

    async def list_for_alert(self, alert_id: UUID) -> list[AlertAcknowledgement]:
        """Every acknowledgement recorded for *alert_id*, oldest first."""
        stmt = (
            self._base_select()
            .where(AlertAcknowledgement.alert_id == alert_id)
            .order_by(AlertAcknowledgement.acknowledged_at.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_first_for_alert(self, alert_id: UUID) -> AlertAcknowledgement | None:
        """Return *alert_id*'s own earliest acknowledgement, or ``None``.

        Backs the MTTA ("mean time to acknowledge") analytics figure,
        which measures the *first* human response, not the latest.
        """
        records = await self.list_for_alert(alert_id)
        return records[0] if records else None


__all__ = ["AlertAcknowledgementRepository"]
