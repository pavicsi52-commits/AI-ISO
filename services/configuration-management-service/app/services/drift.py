"""Drift detection between desired and actual configuration state.

Per docs/039 "DRIFT DETECTION" "Detect": Missing Configuration,
Unexpected Changes, Unauthorized Changes, Version Drift, Policy Drift,
Template Drift, Variable Drift, "Schedule Periodic Drift Analysis" (the
periodic scan itself is :mod:`app.workers.drift_worker`; this service
only records/resolves individual drift instances).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.events.base import DomainEvent

from app.events.configuration_events import DriftDetectedEvent
from app.models.configuration_drift import ConfigurationDrift
from app.models.enums import DriftStatus, DriftType
from app.repositories.configuration_drift import ConfigurationDriftRepository

EventPublisher = Callable[[DomainEvent], Awaitable[None]]


class ConfigurationDriftService:
    """Records, lists, and resolves configuration drift instances."""

    def __init__(
        self,
        drift: ConfigurationDriftRepository,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._drift = drift
        self._publish_event = publish_event

    async def _publish(self, event: DomainEvent) -> None:
        if self._publish_event is not None:
            await self._publish_event(event)

    async def list_for_profile(self, profile_id: UUID) -> list[ConfigurationDrift]:
        """Every drift instance detected for *profile_id*, newest first."""
        return await self._drift.list_for_profile(profile_id)

    async def list_unresolved_for_org(self, organization_id: UUID) -> list[ConfigurationDrift]:
        """Every not-yet-resolved drift instance for *organization_id*."""
        return await self._drift.list_unresolved_for_org(organization_id)

    async def report(
        self,
        *,
        organization_id: UUID,
        profile_id: UUID,
        managed_asset_id: UUID,
        drift_type: DriftType,
        details: dict[str, Any],
    ) -> ConfigurationDrift:
        """Record a newly detected drift instance ("Detect"), publishing ``DriftDetected``."""
        drift = await self._drift.create(
            ConfigurationDrift(
                organization_id=organization_id,
                profile_id=profile_id,
                managed_asset_id=managed_asset_id,
                drift_type=drift_type,
                status=DriftStatus.DETECTED,
                detected_at=datetime.now(UTC),
                details=details,
            )
        )
        await self._publish(
            DriftDetectedEvent(
                source_service="configuration-management-service",
                payload={
                    "drift_id": str(drift.id),
                    "profile_id": str(profile_id),
                    "managed_asset_id": str(managed_asset_id),
                    "drift_type": str(drift_type),
                },
            )
        )
        return drift

    async def resolve(
        self, drift_id: UUID, *, status: DriftStatus, resolved_by: UUID | None
    ) -> ConfigurationDrift:
        """Transition a drift instance to ``RESOLVED``/``IGNORED``/``ACKNOWLEDGED``."""
        drift = await self._drift.require_by_id(drift_id)
        drift.status = status
        if status is DriftStatus.RESOLVED:
            drift.resolved_at = datetime.now(UTC)
            drift.resolved_by = resolved_by
        return await self._drift.update(drift)


__all__ = ["ConfigurationDriftService"]
