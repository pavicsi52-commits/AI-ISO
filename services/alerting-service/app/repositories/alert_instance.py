"""Repository for :class:`app.models.alert_instance.AlertInstance`."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.enums.severity import Severity
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert_instance import AlertInstance
from app.models.enums import AlertStatus

OPEN_STATUSES = (
    AlertStatus.NEW,
    AlertStatus.OPEN,
    AlertStatus.ACKNOWLEDGED,
    AlertStatus.INVESTIGATING,
    AlertStatus.ESCALATED,
)
"""Every status an alert can hold while still demanding attention --
i.e. not ``SUPPRESSED``/``RESOLVED``/``CLOSED``/``EXPIRED``. Used by
both the "open alerts" listing and the analytics rollup so the two can
never disagree about what "open" means.
"""


class AlertInstanceRepository(BaseRepository[AlertInstance]):
    """CRUD plus lookup for :class:`AlertInstance`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AlertInstance, tenant_scope=tenant_scope)

    async def list_for_org(
        self,
        organization_id: UUID,
        *,
        status: AlertStatus | None = None,
        severity: Severity | None = None,
    ) -> list[AlertInstance]:
        """Every alert for *organization_id*, most recently triggered first."""
        stmt = self._base_select().where(AlertInstance.organization_id == organization_id)
        if status is not None:
            stmt = stmt.where(AlertInstance.status == status)
        if severity is not None:
            stmt = stmt.where(AlertInstance.severity == severity)
        stmt = stmt.order_by(AlertInstance.triggered_at.desc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_open_for_org(self, organization_id: UUID) -> list[AlertInstance]:
        """Every still-demanding-attention alert for *organization_id*."""
        stmt = self._base_select().where(
            AlertInstance.organization_id == organization_id,
            AlertInstance.status.in_(OPEN_STATUSES),
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_active_by_fingerprint(
        self, organization_id: UUID, fingerprint: str, *, since: datetime | None = None
    ) -> AlertInstance | None:
        """Return the most recent still-open alert matching *fingerprint*.

        Backs "Duplicate Detection"/"Time Window Deduplication" -- an
        already-resolved alert is deliberately NOT a deduplication
        match, since a condition that recurs after being resolved is a
        genuinely new occurrence, not a duplicate of the old one.
        """
        stmt = self._base_select().where(
            AlertInstance.organization_id == organization_id,
            AlertInstance.fingerprint == fingerprint,
            AlertInstance.status.in_(OPEN_STATUSES),
        )
        if since is not None:
            stmt = stmt.where(AlertInstance.triggered_at >= since)
        stmt = stmt.order_by(AlertInstance.triggered_at.desc())
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_triggered_between(
        self, organization_id: UUID, start: datetime, end: datetime
    ) -> list[AlertInstance]:
        """Every alert triggered within a window ("Time Correlation")."""
        stmt = self._base_select().where(
            AlertInstance.organization_id == organization_id,
            AlertInstance.triggered_at >= start,
            AlertInstance.triggered_at <= end,
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["OPEN_STATUSES", "AlertInstanceRepository"]
