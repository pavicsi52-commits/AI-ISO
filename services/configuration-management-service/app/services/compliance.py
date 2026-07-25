"""Compliance evaluation against configuration profiles.

Per docs/039 "COMPLIANCE" "Evaluate": Security Compliance, Configuration
Compliance, Baseline Compliance, Policy Compliance, Environment
Compliance, Industry Standards, "Generate Compliance Reports" (report
generation itself is :class:`app.services.report.ConfigurationReportService`).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.events.base import DomainEvent

from app.events.configuration_events import ComplianceFailedEvent
from app.models.configuration_compliance import ConfigurationCompliance
from app.models.enums import ComplianceEvalType, ComplianceStatus
from app.repositories.configuration_compliance import ConfigurationComplianceRepository
from app.repositories.configuration_profile import ConfigurationProfileRepository

EventPublisher = Callable[[DomainEvent], Awaitable[None]]

_FAILING_STATUSES = frozenset(
    {ComplianceStatus.NON_COMPLIANT, ComplianceStatus.PARTIALLY_COMPLIANT}
)


class ConfigurationComplianceService:
    """Records and lists compliance evaluations for configuration profiles."""

    def __init__(
        self,
        compliance: ConfigurationComplianceRepository,
        profiles: ConfigurationProfileRepository,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._compliance = compliance
        self._profiles = profiles
        self._publish_event = publish_event

    async def _publish(self, event: DomainEvent) -> None:
        if self._publish_event is not None:
            await self._publish_event(event)

    async def list_for_profile(
        self, profile_id: UUID, *, eval_type: ComplianceEvalType | None = None
    ) -> list[ConfigurationCompliance]:
        """Every compliance evaluation for *profile_id*, newest first."""
        return await self._compliance.list_for_profile(profile_id, eval_type=eval_type)

    async def evaluate(
        self,
        *,
        profile_id: UUID,
        eval_type: ComplianceEvalType,
        status: ComplianceStatus,
        details: dict[str, Any],
        exception_reason: str | None,
    ) -> ConfigurationCompliance:
        """Record a compliance evaluation result ("Evaluate"), publishing
        ``ComplianceFailed`` when *status* is non-compliant or partially
        compliant and no *exception_reason* covers it.
        """
        profile = await self._profiles.require_by_id(profile_id)
        evaluation = await self._compliance.create(
            ConfigurationCompliance(
                organization_id=profile.organization_id,
                profile_id=profile_id,
                eval_type=eval_type,
                status=status,
                checked_at=datetime.now(UTC),
                details=details,
                exception_reason=exception_reason,
            )
        )
        if status in _FAILING_STATUSES and exception_reason is None:
            await self._publish(
                ComplianceFailedEvent(
                    source_service="configuration-management-service",
                    payload={
                        "compliance_id": str(evaluation.id),
                        "profile_id": str(profile_id),
                        "eval_type": str(eval_type),
                        "status": str(status),
                    },
                )
            )
        return evaluation


__all__ = ["ConfigurationComplianceService"]
