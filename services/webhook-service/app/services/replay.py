"""Replay job management (docs/057 "REPLAY")."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.exceptions.validation import ValidationError

from app.models.enums import ReplayScope, ReplayStatus
from app.models.event import WebhookEvent
from app.models.replay import WebhookReplayJob
from app.replay import engine as replay_engine
from app.repositories.event import WebhookEventRepository
from app.repositories.replay import WebhookReplayJobRepository
from app.services.delivery import DeliveryService


class ReplayService:
    """Requests to redeliver a past slice of events, and their own execution."""

    def __init__(
        self,
        replay_jobs: WebhookReplayJobRepository,
        events: WebhookEventRepository,
        delivery: DeliveryService,
    ) -> None:
        self._replay_jobs = replay_jobs
        self._events = events
        self._delivery = delivery

    async def create(
        self,
        organization_id: UUID,
        *,
        scope: ReplayScope,
        event_id: UUID | None = None,
        endpoint_id: UUID | None = None,
        subscription_id: UUID | None = None,
        date_range_start: datetime | None = None,
        date_range_end: datetime | None = None,
        dry_run: bool = False,
        requested_by: str | None = None,
    ) -> WebhookReplayJob:
        """Register a new replay job.

        Raises:
            ValidationError: If the request's own fields don't match
                what its *scope* requires.
        """
        request = replay_engine.ReplayRequest(
            scope=scope,
            event_id=str(event_id) if event_id else None,
            endpoint_id=str(endpoint_id) if endpoint_id else None,
            subscription_id=str(subscription_id) if subscription_id else None,
            date_range_start=date_range_start,
            date_range_end=date_range_end,
        )
        errors = replay_engine.validate_replay_request(request)
        if errors:
            raise ValidationError("; ".join(errors))

        return await self._replay_jobs.create(
            WebhookReplayJob(
                organization_id=organization_id,
                scope=scope,
                event_id=event_id,
                endpoint_id=endpoint_id,
                subscription_id=subscription_id,
                date_range_start=date_range_start,
                date_range_end=date_range_end,
                dry_run=dry_run,
                requested_by=requested_by,
            )
        )

    async def get(self, organization_id: UUID, job_id: UUID) -> WebhookReplayJob:
        """One replay job.

        Raises:
            NotFoundError: If it does not exist here.
        """
        return await self._replay_jobs.require_in_org(organization_id, job_id)

    async def list_jobs(self, organization_id: UUID) -> list[WebhookReplayJob]:
        """Replay jobs in this organization, newest first."""
        return await self._replay_jobs.list_for_org(organization_id)

    async def _matching_events(self, job: WebhookReplayJob) -> list[WebhookEvent]:
        if job.scope == ReplayScope.BY_EVENT:
            if job.event_id is None:
                raise ValidationError("Replay job has scope BY_EVENT but no event_id.")
            return [await self._events.require_in_org(job.organization_id, job.event_id)]
        if job.scope == ReplayScope.BY_DATE_RANGE:
            return await self._events.list_for_org(
                job.organization_id,
                since=job.date_range_start,
                until=job.date_range_end,
                limit=10_000,
            )
        # BY_ENDPOINT and BY_SUBSCRIPTION both replay every event in the
        # organization within this job's own date bounds (unbounded if
        # none given) -- narrowing to the specific endpoint/subscription
        # happens naturally in `DeliveryService.fan_out`'s own
        # subscription-matching, not here.
        return await self._events.list_for_org(
            job.organization_id, since=job.date_range_start, until=job.date_range_end, limit=10_000
        )

    async def preview(self, organization_id: UUID, job_id: UUID) -> dict[str, Any]:
        """How many events this job would replay, without replaying them."""
        job = await self.get(organization_id, job_id)
        events = await self._matching_events(job)
        return {"matched_count": len(events), "event_ids": [str(e.id) for e in events[:50]]}

    async def run(self, organization_id: UUID, job_id: UUID) -> WebhookReplayJob:
        """Execute a replay job: re-fan-out every matching event.

        A dry-run job only computes and stores its own preview; it is
        marked ``COMPLETED`` without ever creating a delivery.
        """
        job = await self.get(organization_id, job_id)
        job.status = ReplayStatus.RUNNING
        job.started_at = datetime.now(UTC)
        await self._replay_jobs.update(job)

        try:
            events = await self._matching_events(job)
            job.matched_count = len(events)
            if job.dry_run:
                job.preview = {"event_ids": [str(e.id) for e in events[:50]]}
            else:
                replayed = 0
                failed = 0
                for event in events:
                    try:
                        await self._delivery.fan_out(organization_id, event, replay_job_id=job.id)
                        replayed += 1
                    except Exception as exc:
                        failed += 1
                        job.error = str(exc)
                job.replayed_count = replayed
                job.failed_count = failed
            job.status = ReplayStatus.COMPLETED
        except Exception as exc:
            job.status = ReplayStatus.FAILED
            job.error = str(exc)
        job.completed_at = datetime.now(UTC)
        return await self._replay_jobs.update(job)


__all__ = ["ReplayService"]
