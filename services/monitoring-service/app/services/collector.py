"""Distributed collector configuration CRUD ("Distributed Collectors")."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.enums import MonitoringTargetType
from app.models.monitoring_collector import MonitoringCollector
from app.repositories.monitoring_collector import MonitoringCollectorRepository


class MonitoringCollectorService:
    """Creates and reads distributed collector configurations."""

    def __init__(self, collectors: MonitoringCollectorRepository) -> None:
        self._collectors = collectors

    async def get_by_id(self, collector_id: UUID) -> MonitoringCollector:
        """Return the collector identified by *collector_id*.

        Raises:
            NotFoundError: If no such collector exists.
        """
        return await self._collectors.require_by_id(collector_id)

    async def list_for_org(self, organization_id: UUID) -> list[MonitoringCollector]:
        """Every collector configuration belonging to *organization_id*."""
        return await self._collectors.list_for_org(organization_id)

    async def list_all_active(self) -> list[MonitoringCollector]:
        """Every active collector, system-wide ("Collector Auto-discovery")."""
        return await self._collectors.list_all_active()

    async def create(
        self,
        *,
        organization_id: UUID,
        name: str,
        collector_key: str,
        target_types: list[MonitoringTargetType],
        parameters: dict[str, Any],
        interval_seconds: float,
        is_active: bool,
    ) -> MonitoringCollector:
        """Register a new distributed collector."""
        return await self._collectors.create(
            MonitoringCollector(
                organization_id=organization_id,
                name=name,
                collector_key=collector_key,
                target_types=[str(t) for t in target_types],
                parameters=parameters,
                interval_seconds=interval_seconds,
                is_active=is_active,
            )
        )


__all__ = ["MonitoringCollectorService"]
