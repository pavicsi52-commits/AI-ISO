"""The scheduled-flow sweep worker.

Runs every enabled, ``SCHEDULED``-trigger flow whose own
``schedule_interval_seconds`` has elapsed since its last run (or that
has never run), across every organization, in one tick. **Leader-elected**
through ``shared_core.scheduler`` -- see :mod:`app.workers.registrar`.

**One session per flow.** Without this sweep, a scheduled flow would sit
forever with nothing ever calling :meth:`~app.services.flow.FlowService
.run` for it -- the exact "queued but nothing ever picks it up" bug class
already found and fixed once in this platform's own webhook-service
(Prompt 057): a row that can be created in a due-to-run state needs a
worker that actually walks it, not just a caller-triggered path.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from shared_core.logging.logger import get_logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.enums import FlowStatus
from app.repositories.event import ConnectorEventRepository
from app.repositories.flow import ConnectorFlowRepository
from app.repositories.sync import ConnectorSyncJobRepository
from app.repositories.transformation import ConnectorTransformationRepository
from app.services.event import EventService
from app.services.flow import FlowService
from app.services.sync import SyncService
from app.services.transformation import TransformationService
from app.types import EventPublisher

logger = get_logger("app.workers.flow_scheduler_sweep")


class FlowSchedulerSweepWorker:
    """Runs every scheduled flow whose own interval has elapsed."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        max_per_tick: int = 200,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._max_per_tick = max_per_tick
        self._publish = publish_event

    async def run_job(self, _job: object) -> None:
        """Entry point matching ``shared_core.scheduler``'s own ``JobFn``."""
        await self.tick()

    async def tick(self) -> int:
        """Run every due scheduled flow; returns how many were run."""
        candidates = await self._due_flow_ids()
        run = 0
        for flow_id, organization_id in candidates:
            if await self._run_one(flow_id, organization_id):
                run += 1
        logger.info(
            "Flow scheduler sweep complete.",
            extra={"extra_fields": {"candidates": len(candidates), "run": run}},
        )
        return run

    async def _due_flow_ids(self) -> list[tuple[UUID, UUID]]:
        now = datetime.now(UTC)
        async with self._session_factory() as session:
            rows = await ConnectorFlowRepository(session).list_due_for_schedule(
                limit=self._max_per_tick
            )
            due = []
            for row in rows:
                if row.status != FlowStatus.ACTIVE:
                    continue
                interval = timedelta(seconds=row.schedule_interval_seconds or 0)
                if row.last_run_at is None or now - row.last_run_at >= interval:
                    due.append((row.id, row.organization_id))
            return due

    async def _run_one(self, flow_id: UUID, organization_id: UUID) -> bool:
        try:
            async with self._session_factory() as session:
                flows = ConnectorFlowRepository(session)
                transformations = TransformationService(ConnectorTransformationRepository(session))
                sync = SyncService(
                    ConnectorSyncJobRepository(session),
                    transformations,
                    publish_event=self._publish,
                )
                events = EventService(ConnectorEventRepository(session))
                service = FlowService(
                    flows, sync, transformations, events, publish_event=self._publish
                )
                flow = await flows.require_in_org(organization_id, flow_id)
                await service.run(
                    organization_id, flow, context={"organization_id": str(organization_id)}
                )
                await session.commit()
            return True
        except Exception as exc:
            logger.warning(
                "A scheduled flow run failed; the rest of the sweep continues.",
                extra={"extra_fields": {"flow_id": str(flow_id), "error": str(exc)}},
            )
            return False


__all__ = ["FlowSchedulerSweepWorker"]
