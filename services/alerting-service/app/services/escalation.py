"""Escalation policy CRUD plus due-level resolution ("ESCALATION")."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from app.escalation.engine import EscalationLevel, due_level, parse_levels
from app.models.alert_escalation import AlertEscalationPolicy
from app.models.alert_instance import AlertInstance
from app.repositories.alert_escalation import AlertEscalationPolicyRepository
from app.schemas.escalation import EscalationLevelRequest


class AlertEscalationPolicyService:
    """Creates and reads escalation policies, and resolves the due level."""

    def __init__(self, policies: AlertEscalationPolicyRepository) -> None:
        self._policies = policies

    async def get_by_id(self, policy_id: UUID) -> AlertEscalationPolicy:
        """Return the policy identified by *policy_id*.

        Raises:
            NotFoundError: If no such policy exists.
        """
        return await self._policies.require_by_id(policy_id)

    async def list_for_org(self, organization_id: UUID) -> list[AlertEscalationPolicy]:
        """Every escalation policy belonging to *organization_id*."""
        return await self._policies.list_for_org(organization_id)

    async def list_enabled_for_org(self, organization_id: UUID) -> list[AlertEscalationPolicy]:
        """Every enabled escalation policy for *organization_id*."""
        return await self._policies.list_enabled_for_org(organization_id)

    async def create(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        name: str,
        levels: Sequence[EscalationLevelRequest],
        enabled: bool,
    ) -> AlertEscalationPolicy:
        """Create an escalation policy from an ordered level chain."""
        return await self._policies.create(
            AlertEscalationPolicy(
                organization_id=organization_id,
                project_id=project_id,
                name=name,
                levels=[
                    {
                        "target_type": str(level.target_type),
                        "target_reference": level.target_reference,
                        "delay_seconds": level.delay_seconds,
                    }
                    for level in levels
                ],
                enabled=enabled,
            )
        )

    def levels_for(self, policy: AlertEscalationPolicy) -> list[EscalationLevel]:
        """The policy's own stored JSON levels, validated into a typed chain."""
        return parse_levels(policy.levels)

    def due_level_for_alert(
        self,
        policy: AlertEscalationPolicy,
        alert: AlertInstance,
        *,
        moment: datetime | None = None,
    ) -> EscalationLevel | None:
        """Return the escalation level due for *alert* under *policy*."""
        now = moment or datetime.now(UTC)
        elapsed = (now - alert.triggered_at).total_seconds()
        return due_level(self.levels_for(policy), elapsed)


__all__ = ["AlertEscalationPolicyService"]
