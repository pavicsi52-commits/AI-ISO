"""The maintenance worker: expire approvals, roll quota periods, sweep retention.

Three jobs that share one property -- each one keeps a table honest, and
each one's failure mode is silent.

- **An expired approval left pending** is an actionable item on somebody's
  list that can never complete. A queue full of those stops being read.
- **A quota whose period ended** keeps reporting last month's usage, so
  every figure derived from it is wrong until something touches it.
- **Decisions past retention** grow without bound; this is the only thing
  that removes them.

**Leader-elected** through ``shared_core.scheduler`` -- see
:mod:`app.workers.registrar`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from shared_core.logging.logger import get_logger
from shared_core.notifications.factory import create_notification_framework
from shared_core.scheduler import Job
from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config.settings import PolicyEngineServiceSettings
from app.models.policy import Policy
from app.notifications.policy_notifications import PolicyNotificationService
from app.repositories.runtime import (
    PolicyApprovalRepository,
    PolicyDecisionRepository,
    PolicyQuotaRepository,
)
from app.services.approval import ApprovalService
from app.services.quota import QuotaService

logger = get_logger("app.workers.maintenance")


async def _no_events(_event: object) -> None:
    """Swallow domain events raised from a background sweep.

    A sweep expiring two hundred stale approvals would otherwise publish
    two hundred events describing paperwork nobody asked about, drowning
    the ones that describe something a subscriber can act on. The state
    change is recorded on the rows either way.
    """


class MaintenanceWorker:
    """Expires approvals, rolls quota periods, and enforces retention."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        graph_settings: PolicyEngineServiceSettings,
        max_per_tick: int = 200,
    ) -> None:
        self._session_factory = session_factory
        self._settings = graph_settings
        self._max_per_tick = max_per_tick

    async def run_job(self, _job: Job) -> None:
        """Entry point matching ``shared_core.scheduler``'s own ``JobFn``."""
        await self.tick()

    async def tick(self) -> dict[str, int]:
        """Sweep every organization; returns what was done."""
        organizations = await self._organizations()
        totals = {"expired_approvals": 0, "rolled_quotas": 0, "purged_decisions": 0}

        for organization_id in organizations:
            outcome = await self._sweep(organization_id)
            for key, value in outcome.items():
                totals[key] += value

        logger.info(
            "Policy maintenance sweep complete.",
            extra={"extra_fields": {"organizations": len(organizations), **totals}},
        )
        return totals

    async def _organizations(self) -> list[UUID]:
        """Every organization with a policy catalogue."""
        async with self._session_factory() as session:
            statement = (
                select(distinct(Policy.organization_id))
                .where(Policy.deleted_at.is_(None))
                .limit(self._max_per_tick)
            )
            result = await session.execute(statement)
            return [row for row in result.scalars().all() if row is not None]

    async def _sweep(self, organization_id: UUID) -> dict[str, int]:
        """Sweep one organization under its own session.

        A failure on one tenant is logged and skipped rather than allowed
        to abort the tick -- the next tenant's approvals still need
        expiring.
        """
        outcome = {"expired_approvals": 0, "rolled_quotas": 0, "purged_decisions": 0}
        try:
            async with self._session_factory() as session:
                notifications = PolicyNotificationService(create_notification_framework())

                approvals = ApprovalService(
                    PolicyApprovalRepository(session),
                    notifications,
                    publish_event=_no_events,
                    expiry_hours=self._settings.approval_expiry_hours,
                    emergency_enabled=self._settings.emergency_approval_enabled,
                )
                outcome["expired_approvals"] = await approvals.sweep_expired(organization_id)

                quotas = QuotaService(
                    PolicyQuotaRepository(session),
                    notifications,
                    publish_event=_no_events,
                    warning_threshold=self._settings.quota_warning_threshold,
                )
                outcome["rolled_quotas"] = await quotas.sweep_periods(organization_id)

                decisions = PolicyDecisionRepository(session)
                cutoff = datetime.now(UTC) - timedelta(days=self._settings.decision_retention_days)
                outcome["purged_decisions"] = await decisions.purge_older_than(
                    organization_id, cutoff=cutoff
                )

                await session.commit()
        except Exception as exc:
            logger.warning(
                "A policy maintenance sweep failed; the rest of the tick continues.",
                extra={
                    "extra_fields": {
                        "organization_id": str(organization_id),
                        "error": str(exc),
                    }
                },
            )
        return outcome


__all__ = ["MaintenanceWorker"]
