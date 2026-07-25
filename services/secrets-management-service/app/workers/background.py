"""A lightweight in-process interval loop for background checks
("Background rotation workers", docs/035 "PERFORMANCE").

Deliberately not the full distributed
:mod:`shared_core.scheduler` framework (leader election, heartbeat,
failover) -- this service doesn't yet run multi-replica deployments
that would need leader election, matching
``services/project-service``'s identical "in-process worker, not a
separate deployable process" choice for its own background concerns.
Each check function is re-resolved (fresh services, fresh session) on
every tick via *build_and_run*, so a failed iteration never leaves a
stale, half-committed unit of work sitting open across ticks.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from shared_core.logging.logger import get_logger

logger = get_logger("app.workers.background")


async def run_periodic(
    name: str, interval_seconds: int, build_and_run: Callable[[], Awaitable[None]]
) -> None:
    """Call *build_and_run* every *interval_seconds*, forever, until cancelled.

    A single failed iteration is logged and does not stop the loop.
    """
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            await build_and_run()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning(
                "Background task iteration failed.", extra={"extra_fields": {"task": name}}
            )


__all__ = ["run_periodic"]
