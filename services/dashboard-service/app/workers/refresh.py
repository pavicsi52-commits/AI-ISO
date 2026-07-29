"""The per-replica live-refresh loop ("REAL-TIME UPDATES", "Auto Refresh").

**This worker is deliberately not leader-elected.** Every other
recurring job in this platform runs on exactly one replica, because
running it N times would duplicate work. This one is the opposite case:
subscribers live in the *process* that accepted their connection, so a
single elected replica would notify only its own watchers and leave
everyone connected to the other replicas frozen on stale data. Each
replica therefore runs its own loop over its own subscribers, and the
duplication is the point rather than a bug.

**It notifies; it does not fetch.** The loop pushes a "your view is
stale, re-fetch" frame and nothing more. It holds no user's bearer
token, and every widget in this service is resolved with the *viewing
user's own* token -- so a worker that resolved data centrally and
broadcast it would hand whatever one credential could see to every
watcher of the dashboard. See :mod:`app.services.streaming`. The
consequence is that this worker needs no database session, no HTTP
client, and no data-source credentials at all, which is a good sign the
shape is right.

**Nothing is notified for a dashboard nobody is watching.** The loop
iterates :meth:`~app.realtime.hub.DashboardHub.watched_dashboards`, not
the dashboards table, so its cost is proportional to the live audience
rather than to the size of the installation.
"""

from __future__ import annotations

import asyncio
import contextlib
import time

from shared_core.logging.logger import get_logger

from app.realtime.hub import DashboardHub

logger = get_logger("app.workers.refresh")


class RefreshWorker:
    """Tells watched dashboards' subscribers to re-fetch, on a timer."""

    def __init__(
        self,
        hub: DashboardHub,
        *,
        poll_seconds: float = 15.0,
        max_per_tick: int = 500,
    ) -> None:
        self._hub = hub
        self._poll_seconds = poll_seconds
        self._max_per_tick = max_per_tick
        self._task: asyncio.Task[None] | None = None

    @property
    def running(self) -> bool:
        """Whether the loop is currently active."""
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        """Begin the refresh loop; idempotent."""
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        """Stop the refresh loop and drop every subscriber."""
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        await self._hub.close_all()

    async def tick(self) -> int:
        """Notify every watched dashboard once; returns how many were notified.

        Zero is the normal outcome on a replica with no live viewers,
        and it costs one dictionary read rather than a database query.
        """
        watched = self._hub.watched_dashboards()[: self._max_per_tick]
        if not watched:
            return 0

        started = time.monotonic()
        notified = 0
        for dashboard_id in watched:
            try:
                delivered = await self._hub.publish_update(
                    dashboard_id, {"action": "reload", "reason": "refresh_due"}
                )
            except Exception as exc:
                logger.warning(
                    "Could not notify a dashboard's watchers; the tick continues.",
                    extra={"extra_fields": {"dashboard_id": str(dashboard_id), "error": str(exc)}},
                )
                continue
            if delivered:
                notified += 1

        logger.debug(
            "Refresh tick complete.",
            extra={
                "extra_fields": {
                    "watched": len(watched),
                    "notified": notified,
                    "duration_ms": round((time.monotonic() - started) * 1000, 1),
                }
            },
        )
        return notified

    async def _loop(self) -> None:
        """Tick forever until cancelled."""
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "The dashboard refresh loop raised; it will keep running.",
                    extra={"extra_fields": {"error": str(exc)}},
                )
            await asyncio.sleep(self._poll_seconds)


__all__ = ["RefreshWorker"]
