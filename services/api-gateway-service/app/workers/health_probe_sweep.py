"""The health-probe sweep worker.

Probes every instance of every registered backend service, across every
organization. **Leader-elected** through ``shared_core.scheduler`` -- see
:mod:`app.workers.registrar`.

**One session per instance probe.** A single unreachable instance (a DNS
failure, a hung connection) must not poison the transaction the next
instance's own probe needs, and an instance silently skipped is worse
than one that visibly failed.

**Shares its circuit breakers with the live proxy path.** The same
``app.state.circuit_breakers`` dict this worker mutates is also read and
written by every request-scoped :class:`~app.services.health
.HealthMonitorService` the proxy builds per call -- a breaker this sweep
trips is a breaker the very next proxied request already sees as open,
without waiting for that request's own failure to trip it independently.

**Publishes ``GatewayHealthChangedEvent`` only on an actual transition.**
This is the one place a status change is ever detected (every other
health read is a snapshot of whatever this sweep last persisted), so it
is also the only correct place to raise the event docs/056 names for it.
"""

from __future__ import annotations

from uuid import UUID

from shared_core.connectors.retry import CircuitBreaker
from shared_core.logging.logger import get_logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config.settings import GatewayServiceSettings
from app.events.gateway_events import SOURCE_SERVICE, GatewayHealthChangedEvent
from app.repositories.health import ApiServiceHealthRepository
from app.repositories.service import ApiServiceRepository
from app.services.health import HealthMonitorService
from app.types import EventPublisher

logger = get_logger("app.workers.health_probe_sweep")


class HealthProbeSweepWorker:
    """Probes every backend instance and persists its own latest health."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        breakers: dict[str, CircuitBreaker],
        settings: GatewayServiceSettings,
        *,
        max_services_per_tick: int = 200,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._breakers = breakers
        self._settings = settings
        self._max_services_per_tick = max_services_per_tick
        self._publish = publish_event

    async def run_job(self, _job: object) -> None:
        """Entry point matching ``shared_core.scheduler``'s own ``JobFn``."""
        await self.tick()

    async def tick(self) -> int:
        """Probe every instance; returns how many probes succeeded."""
        targets = await self._targets()
        probed = 0
        for organization_id, service_id, service_name, instance_url in targets:
            if await self._probe_one(organization_id, service_id, service_name, instance_url):
                probed += 1
        logger.info(
            "Health probe sweep complete.",
            extra={"extra_fields": {"instances": len(targets), "probed": probed}},
        )
        return probed

    async def _targets(self) -> list[tuple[UUID, UUID, str, str]]:
        """Every enabled service's own instance, across every organization."""
        async with self._session_factory() as session:
            services = await ApiServiceRepository(session).list_all(limit=self._max_services_per_tick)
        return [
            (service.organization_id, service.id, service.name, instance["url"])
            for service in services
            if service.enabled
            for instance in service.instances
        ]

    async def _probe_one(
        self, organization_id: UUID, service_id: UUID, service_name: str, instance_url: str
    ) -> bool:
        """Probe one instance under its own session."""
        try:
            async with self._session_factory() as session:
                health_repo = ApiServiceHealthRepository(session)
                previous = await health_repo.get_for_instance(organization_id, service_id, instance_url)
                previous_status = previous.status if previous is not None else None

                monitor = HealthMonitorService(
                    health_repo,
                    failure_threshold=self._settings.circuit_breaker_failure_threshold,
                    recovery_seconds=self._settings.circuit_breaker_recovery_seconds,
                    probe_timeout_seconds=self._settings.health_probe_timeout_seconds,
                    breakers=self._breakers,
                )
                probed = await monitor.probe(
                    organization_id, service_id, instance_url, service_name=service_name
                )
                await session.commit()

            if self._publish is not None and probed.status != previous_status:
                await self._publish(
                    GatewayHealthChangedEvent(
                        source_service=SOURCE_SERVICE,
                        organization_id=organization_id,
                        payload={
                            "service_id": str(service_id),
                            "instance_url": instance_url,
                            "previous_status": str(previous_status) if previous_status else None,
                            "status": str(probed.status),
                        },
                    )
                )
            return True
        except Exception as exc:
            logger.warning(
                "A backend instance probe failed; the rest of the sweep continues.",
                extra={
                    "extra_fields": {
                        "organization_id": str(organization_id),
                        "service_id": str(service_id),
                        "instance_url": instance_url,
                        "error": str(exc),
                    }
                },
            )
            return False


__all__ = ["HealthProbeSweepWorker"]
